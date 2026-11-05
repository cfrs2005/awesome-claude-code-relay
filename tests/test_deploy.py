#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署链路的护栏测试。

这里的断言几乎全是「防止有人把危险写法改回去」：
`sudo bash <脚本>`、上传到 /tmp、备份先删后拷、重启失败不回滚 ——
每一条都曾经真实存在于这个仓库里，或者差一点就写进去。
"""
import re

from helpers import ROOT

DEPLOY_SH = ROOT / "scripts" / "deploy.sh"
DEPLOY_YML = ROOT / ".github" / "workflows" / "deploy.yml"


def sh():
    return DEPLOY_SH.read_text(encoding="utf-8")


def yml():
    return DEPLOY_YML.read_text(encoding="utf-8")


def _code(text):
    """去掉整行注释：脚本与 workflow 的注释里会成段引用「危险写法」，不该被当成代码。"""
    return "\n".join(ln for ln in text.splitlines()
                     if not ln.lstrip().startswith("#"))


def _array(name):
    m = re.search(rf"^{name}=\((.*)\)$", sh(), re.M)
    assert m, f"deploy.sh 里找不到 {name}"
    return m.group(1).split()


# ------------------------------------------------------------ 权限模型 ----

def test_only_restart_needs_privilege():
    """脚本里每一处 sudo 都必须是那条唯一的白名单命令。"""
    lines = [ln.strip() for ln in _code(sh()).splitlines() if re.search(r"\bsudo\b", ln)]
    assert lines, "预期脚本里至少有重启用的 sudo"
    for ln in lines:
        tail = ln.split("sudo ", 1)[1]
        assert tail.startswith('systemctl restart "$SERVICE"'), \
            f"出现了白名单之外的提权：{ln}"


def test_service_name_matches_sudoers_string():
    """sudoers 是按字符串精确匹配的，少个 .service 就会变成要密码。"""
    assert 'SERVICE="${SERVICE:-mq-hub.service}"' in sh()
    assert "/usr/bin/systemctl restart mq-hub.service" in yml()


def test_workflow_never_runs_script_as_root():
    assert "sudo bash" not in _code(yml()), "不允许把上传的脚本交给 root 执行"


def test_upload_target_is_not_world_writable():
    text = _code(yml())
    assert "/tmp/" not in text, "不要往 /tmp 上传（全局可写，存在替换窗口）"
    assert 'incoming/"' in text, "应上传到部署账号家目录下的 incoming/"


def test_workflow_checks_server_is_prepared():
    """提前确认可写与 sudo 白名单，别等到「文件已铺开、重启失败」才发现。"""
    text = _code(yml())
    assert "test -w" in text
    assert "sudo -n -l" in text


# ---------------------------------------------------------------- 版本 ----

def test_version_is_validated_before_use():
    text = _code(yml())
    assert r"[0-9]+\.[0-9]+\.[0-9]+" in text, "缺少版本号格式校验"
    doc = __import__("yaml").safe_load(text)
    inputs = doc[True]["workflow_dispatch"]["inputs"]  # YAML 1.1 把 on 解析成 True
    assert "version" in inputs, "手动触发必须能指定版本号，不能用分支名兜底"


def test_script_also_rejects_bad_version():
    """两道卡：workflow 卡一次，脚本自己再卡一次（脚本也可能被手工调用）。"""
    assert '^v[0-9]+\\.[0-9]+\\.[0-9]+$' in sh()


# ---------------------------------------------------------------- 备份 ----

def test_backup_is_atomic():
    """旧写法先 rm 再 cp：拷贝失败就把回滚基准物理删了。"""
    text = sh()
    assert "BACKUP_TMP=" in text and ".prev.tmp" in text
    assert 'mv "$BACKUP_TMP" "$BACKUP"' in text
    assert 'rm -rf "$BACKUP/$d"' not in text, "备份阶段不允许先删后拷"


def test_version_written_atomically():
    """历史 VERSION 可能是 root:644，直接 > 重定向会 EACCES。"""
    text = sh()
    assert ".VERSION.tmp" in text
    assert 'mv "$APP_DIR/.VERSION.tmp" "$APP_DIR/VERSION"' in text


# ---------------------------------------------------------------- 回滚 ----

def test_every_failure_after_backup_rolls_back():
    text = sh()
    assert "trap 'restore' ERR" in text
    assert 'sudo systemctl restart "$SERVICE" || restore' in text
    # 回滚路径自己也要能重启，否则恢复了文件但服务还跑着坏代码
    restore_body = text.split("restore() {", 1)[1].split("\n}", 1)[0]
    assert "sudo systemctl restart" in restore_body


def test_restore_cannot_recurse():
    assert "RESTORING" in sh(), "回滚里失败再触发回滚会无限递归"


def test_tar_entries_are_validated():
    text = sh()
    assert "tar -tzf" in text
    assert r"(^|/)\.\.(/|$)" in text, "缺少 .. 逃逸检查"


# ------------------------------------------------------------ 清单一致 ----

def test_backup_list_matches_package_contents():
    """deploy.sh 的备份白名单是手工维护的，打包清单变了它不会跟着变。"""
    packaged = yml().split("Build release package", 1)[1].split("Set up SSH", 1)[0]
    for name in _array("FILES"):
        if name == "VERSION":
            continue  # 由 deploy.sh 自己写，不在包里
        assert name in packaged, f"{name} 在备份白名单里，但打包步骤没有它"
    for d in _array("DIRS"):
        assert f"{d}/" in packaged, f"目录 {d} 在备份白名单里，但打包步骤没有它"
