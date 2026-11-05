#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作流静态检查。

为什么不用 act：这些 workflow 依赖 GitHub 上下文、secrets 与 PAT，
本地跑不出真结果，但**语法错和曾经踩过的坑可以静态守住**。
历史上的 heredoc EOF 语法错误连修两个提交才修对，就是缺这一层。
"""
import re
import subprocess
import tempfile

import pytest
import yaml

from helpers import ROOT

WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_blocks(doc):
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if step.get("run"):
                yield step


def test_all_workflows_parse():
    assert WORKFLOWS, "没有找到任何 workflow"
    for path in WORKFLOWS:
        doc = load(path)
        assert "jobs" in doc, path.name


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_shell_blocks_have_valid_syntax(path):
    doc = load(path)
    for step in run_blocks(doc):
        script = re.sub(r"\$\{\{[^}]*\}\}", "PLACEHOLDER", step["run"])
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(script)
            tmp = fh.name
        proc = subprocess.run(["bash", "-n", tmp], capture_output=True, text=True)
        assert proc.returncode == 0, f"{path.name} / {step.get('name')}: {proc.stderr}"


# ------------------------------------------------------- 回归护栏 --------

def test_comment_trigger_uses_prefix_match():
    """2026-11-04 自触发死循环：contains() 把说明评论里的命令当成了指令。"""
    doc = load(ROOT / ".github" / "workflows" / "providers-check.yml")
    cond = doc["jobs"]["check"]["if"]
    assert "startsWith(" in cond
    assert "contains(github.event.comment.body" not in cond
    # 机器人自己的评论不能回到用户命令路径
    assert "user.type != 'Bot'" in cond


def test_sync_readme_actually_exports_pr_number():
    """曾经 PR 号只写到 PR_URL，子进程拿到空串 → gh pr view "" → 静默跳过回写。"""
    doc = load(ROOT / ".github" / "workflows" / "sync-readme.yml")
    steps = list(run_blocks(doc))
    blob = "\n".join(s["run"] for s in steps)
    assert "PR_NUMBER=$" in blob or 'PR_NUMBER=' in blob, "PR 号没有导出到 GITHUB_ENV"
    assert "GITHUB_ENV" in blob
    assert "scripts/writeback.py" in blob, "回写应走可测脚本，而不是内嵌 heredoc"


def test_sync_readme_fails_loudly():
    doc = load(ROOT / ".github" / "workflows" / "sync-readme.yml")
    names = [s.get("name", "") for s in run_blocks(doc)]
    assert any("Fail visibly" in n for n in names), "回写失败必须让 job 变红"


def test_merge_failure_is_not_swallowed():
    """合并失败原来只打 ::warning，job 仍是绿的。"""
    text = (ROOT / ".github" / "workflows" / "providers-check.yml").read_text(encoding="utf-8")
    merge_block = text.split("Merge PR (squash)", 1)[1]
    assert "exit 1" in merge_block
    assert "::warning::合并失败" not in merge_block


def test_providers_check_declares_concurrency():
    doc = load(ROOT / ".github" / "workflows" / "providers-check.yml")
    assert doc.get("concurrency"), "同一 PR 的检查必须串行，否则评论风暴"


def test_shell_variables_next_to_cjk_are_braced():
    """`$VAR）` 这种写法在部分 locale 下会把中文当成变量名的一部分。

    实测过一次：`log "部署 $VERSION 成功（引擎 $live_engine）"` 在 macOS 的 bash 下
    报 `live_engine： unbound variable`，整个部署脚本直接退出。
    规则：变量后面紧跟非 ASCII 字符时必须写成 ${VAR}。
    """
    pattern = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)(?=[^\x00-\x7f])")
    offenders = []
    candidates = [ROOT / "scripts" / "deploy.sh"] + WORKFLOWS
    for path in candidates:
        for m in pattern.finditer(path.read_text(encoding="utf-8")):
            line = path.read_text(encoding="utf-8")[:m.start()].count("\n") + 1
            offenders.append(f"{path.name}:{line} ${m.group(1)}")
    assert not offenders, "变量后紧跟中文，请加花括号：" + "；".join(offenders)
