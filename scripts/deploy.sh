#!/usr/bin/env bash
# Hub 部署脚本（在服务器上执行，由 .github/workflows/deploy.yml 上传后调用）。
#
# 权限模型（重要）
# ----------------
# 本脚本**以部署账号（非 root）身份运行**，全程只做非特权文件操作。
# 唯一的提权命令是：sudo systemctl restart mq-hub.service
# 因此 sudoers 必须只放行这一条，且字符串与本文件里的调用逐字符一致（含 .service）。
#
# 这条模型挡的是「CI 凭据泄露后的横向移动」和「脚本 bug 打偏毁系统」，
# 挡不住「恶意改 app.py 再重启」——因为服务仍以 root 运行。真正的关闸是
# systemd 的 User=，属后续专项，别把它当成已经解决了。
#
# 布局约定（与现有 systemd 单元一致，不改单元）：
#   /opt/mq-hub/app.py            FastAPI 入口（uvicorn app:app --app-dir /opt/mq-hub）
#   /opt/mq-hub/contracts.py      契约层
#   /opt/mq-hub/render_report.py  报告渲染器
#   /opt/mq-hub/fonts/*.woff2     自托管字体
#   /opt/mq-hub/engine/mq.py      引擎副本（Hub 只跑这份）
#   /opt/mq-hub/providers-index.json  首页目录区数据（部署时生成）
#   /opt/mq-hub/VERSION           部署版本（healthz 会读它）
#   /opt/mq-hub/env               凭证，**root:600，部署账号不可读写**
#   /opt/mq-hub/data              绑定关系与报告存档，**root 所有，部署不碰**
#
# 用法: deploy.sh <tarball> <version>
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/mq-hub}"
SERVICE="${SERVICE:-mq-hub.service}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8710/healthz}"
BACKUP="$APP_DIR/.prev"
BACKUP_TMP="$APP_DIR/.prev.tmp"
FILES=(app.py contracts.py render_report.py providers-index.json VERSION)
DIRS=(engine fonts)

TARBALL="${1:-}"
VERSION="${2:-}"

log() { echo "[deploy] $*"; }
die() { echo "[deploy] $*" >&2; exit 2; }

[ -n "$TARBALL" ] && [ -n "$VERSION" ] || die "用法: deploy.sh <tarball> <version>"
[ -f "$TARBALL" ] || die "找不到发布包: $TARBALL"
# 版本号会被写进 VERSION 并参与 healthz 比对，格式必须在入口就卡死
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "版本号格式不对（应形如 v0.2.0）: $VERSION"

# ---------------------------------------------------------------- 回滚 ----
RESTORING=0
restore() {
  if [ "$RESTORING" = "1" ]; then return 0; fi
  RESTORING=1
  set +e
  log "部署失败，回滚到上一版"
  if [ ! -d "$BACKUP" ]; then
    log "没有可用备份（首次部署），当前文件未恢复，请手动检查 $APP_DIR"
  else
    for f in "${FILES[@]}"; do
      if [ -f "$BACKUP/$f" ]; then cp -a "$BACKUP/$f" "$APP_DIR/$f"; fi
    done
    for d in "${DIRS[@]}"; do
      if [ -d "$BACKUP/$d" ]; then
        rm -rf "${APP_DIR:?}/$d"
        cp -a "$BACKUP/$d" "$APP_DIR/$d"
      fi
    done
  fi
  if sudo systemctl restart "$SERVICE"; then
    log "已回滚并重启服务。请检查 journalctl -u $SERVICE -n 100"
  else
    log "回滚后重启也失败了！请立即手动处理：journalctl -u $SERVICE -n 100"
  fi
  exit 1
}

# ---------------------------------------------------------------- 校验 ----
# 先验证包再动任何东西：坏包不应该连备份都触发一遍。
# tar 成员名形如 ./engine/mq.py，只拒绝绝对路径与 .. 逃逸
log "校验发布包"
bad="$(tar -tzf "$TARBALL" | grep -E '(^/|(^|/)\.\.(/|$))' | head -5 || true)"
if [ -n "$bad" ]; then
  printf '%s\n' "$bad" >&2
  die "发布包含非法路径（绝对路径或 ..），拒绝解包"
fi

# ---------------------------------------------------------------- 备份 ----
# 备份阶段失败时不动应用文件，也不重启服务，所以**不挂 ERR 回滚**，
# 让它以非零码退出即可。只在备份完成、即将改动线上文件时才接管回滚。
log "备份当前版本 → $BACKUP_TMP"
mkdir -p "$APP_DIR"
rm -rf "$BACKUP_TMP"
mkdir -p "$BACKUP_TMP"
for f in "${FILES[@]}"; do
  if [ -f "$APP_DIR/$f" ]; then cp -a "$APP_DIR/$f" "$BACKUP_TMP/$f"; fi
done
for d in "${DIRS[@]}"; do
  if [ -d "$APP_DIR/$d" ]; then cp -a "$APP_DIR/$d" "$BACKUP_TMP/$d"; fi
done
# 原子切换：先写满 .prev.tmp，再换掉 .prev。
# 旧写法是「先 rm 再 cp」，拷贝失败就把上一版备份物理删了 —— 回滚基准被自己毁掉。
rm -rf "$BACKUP"
mv "$BACKUP_TMP" "$BACKUP"

# 从这里开始，任何失败都要回到备份状态
trap 'restore' ERR

# ---------------------------------------------------------------- 解包 ----
log "解包 $TARBALL"
tar -xzf "$TARBALL" -C "$APP_DIR"

# 用 tmp + mv 写 VERSION：历史文件可能是 root:644，直接 > 重定向会 EACCES，
# 而 mv 只需要目录写权限。
printf '%s\n' "$VERSION" > "$APP_DIR/.VERSION.tmp"
mv "$APP_DIR/.VERSION.tmp" "$APP_DIR/VERSION"

# ---------------------------------------------------------------- 重启 ----
log "重启 $SERVICE"
sudo systemctl restart "$SERVICE" || restore

# -------------------------------------------------------- 健康检查 ----
# 三条都要满足：进程活着 / 引擎副本在 / healthz 报的版本就是刚部署的版本。
# 只查 200 是不够的——systemd 起来但加载到旧文件时，200 会骗人。
for i in $(seq 1 20); do
  if body="$(curl -fsS --max-time 3 "$HEALTH_URL" 2>/dev/null)"; then
    verdict="$(printf '%s' "$body" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("bad|"); raise SystemExit(0)
ok = bool(d.get("ok")) and bool(d.get("engine"))
print("%d|%s|%s" % (1 if ok else 0, d.get("version", ""), d.get("engine_version", "")))
' 2>/dev/null || echo "bad||")"
    ok="${verdict%%|*}"
    rest="${verdict#*|}"
    live_version="${rest%%|*}"
    live_engine="${rest#*|}"
    if [ "$ok" = "1" ] && [ "$live_version" = "$VERSION" ]; then
      trap - ERR
      log "✅ 部署 $VERSION 成功（引擎 ${live_engine}）"
      exit 0
    fi
    log "健康检查未就绪（第 $i 次）：$body"
  else
    log "健康检查无响应（第 $i 次）"
  fi
  sleep 1
done

restore
