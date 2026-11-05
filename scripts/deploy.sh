#!/usr/bin/env bash
# Hub 部署脚本（在服务器上执行，由 .github/workflows/deploy.yml 上传后调用）。
#
# 职责：备份当前版本 → 解包 → 重启 → 健康检查 → 失败自动回滚。
#
# 布局约定（与现有 systemd 单元一致，不改单元）：
#   /opt/mq-hub/app.py            FastAPI 入口（uvicorn app:app --app-dir /opt/mq-hub）
#   /opt/mq-hub/contracts.py      契约层
#   /opt/mq-hub/render_report.py  报告渲染器
#   /opt/mq-hub/fonts/*.woff2     自托管字体
#   /opt/mq-hub/engine/mq.py      引擎副本（Hub 只跑这份）
#   /opt/mq-hub/providers-index.json  首页目录区数据（部署时生成）
#   /opt/mq-hub/VERSION           部署版本（healthz 会读它）
#
# 用法: deploy.sh <tarball> <version>
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/mq-hub}"
SERVICE="${SERVICE:-mq-hub}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8710/healthz}"
BACKUP="$APP_DIR/.prev"
FILES=(app.py contracts.py render_report.py providers-index.json VERSION)

TARBALL="${1:-}"
VERSION="${2:-}"
[ -n "$TARBALL" ] && [ -n "$VERSION" ] || { echo "用法: deploy.sh <tarball> <version>" >&2; exit 2; }
[ -f "$TARBALL" ] || { echo "找不到发布包: $TARBALL" >&2; exit 2; }

log() { echo "[deploy] $*"; }

# ---------------------------------------------------------------- 备份 ----
log "备份当前版本到 $BACKUP"
mkdir -p "$APP_DIR" "$BACKUP"
for f in "${FILES[@]}"; do
  if [ -f "$APP_DIR/$f" ]; then cp -a "$APP_DIR/$f" "$BACKUP/$f"; fi
done
for d in engine fonts; do
  if [ -d "$APP_DIR/$d" ]; then
    rm -rf "$BACKUP/$d"
    cp -a "$APP_DIR/$d" "$BACKUP/$d"
  fi
done

# ---------------------------------------------------------------- 解包 ----
log "解包 $TARBALL"
tar -xzf "$TARBALL" -C "$APP_DIR"
printf '%s\n' "$VERSION" > "$APP_DIR/VERSION"

# ---------------------------------------------------------------- 回滚 ----
restore() {
  log "部署失败，回滚到上一版"
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then cp -a "$BACKUP/$f" "$APP_DIR/$f"; fi
  done
  for d in engine fonts; do
    if [ -d "$BACKUP/$d" ]; then
      rm -rf "$APP_DIR/$d"
      cp -a "$BACKUP/$d" "$APP_DIR/$d"
    fi
  done
  systemctl restart "$SERVICE" || true
  log "已回滚。请检查 journalctl -u $SERVICE -n 100"
  exit 1
}

# ---------------------------------------------------------------- 重启 ----
log "重启 $SERVICE"
systemctl restart "$SERVICE"

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
