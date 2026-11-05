#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PR 指引评论：提交者照着这一条就能跑完，不用再读文档。

关键约束：命令里的引擎地址必须是 tag 化的（与 contracts.ENGINE_URL 同源），
否则用户按指引跑出来的是浮动 HEAD，报告里的 engine 字段和行为对不上。
"""
import subprocess
import sys

from helpers import ROOT

import contracts

SCRIPT = ROOT / "scripts" / "pr_guide.py"


def run(repo, tmp_path):
    out = tmp_path / "guide.md"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", repo["base"],
         "--head", repo["head"], "--out", str(out)],
        cwd=repo["path"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return out.read_text(encoding="utf-8")


def test_guide_uses_tag_pinned_engine_url(provider_repo, tmp_path):
    text = run(provider_repo(), tmp_path)
    assert contracts.ENGINE_URL in text
    assert "/main/mq/mq.py" not in text


def test_guide_gives_copyable_command(provider_repo, tmp_path):
    repo = provider_repo(api_base="https://api.demo.example")
    text = run(repo, tmp_path)
    assert "--base-url https://api.demo.example" in text
    assert "--expect-family claude" in text
    assert "--mode standard" in text
    assert "json report.json" in text


def test_guide_warns_quick_mode_is_not_enough(provider_repo, tmp_path):
    text = run(provider_repo(), tmp_path)
    assert "quick" in text
    assert "standard" in text


def test_guide_marks_non_claude_entry(provider_repo, tmp_path):
    """非 Claude 端点必须在指引里点明，否则提交者会以为自己在测 Claude。"""
    text = run(provider_repo(family="openai"), tmp_path)
    assert "openai" in text
    assert "非 Claude" in text


def test_guide_is_empty_without_provider_change(provider_repo, tmp_path):
    repo = provider_repo()
    out = tmp_path / "g.md"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", repo["base"],
         "--head", repo["base"], "--out", str(out)],
        cwd=repo["path"], capture_output=True, text=True)
    assert proc.returncode == 0
    assert out.read_text(encoding="utf-8") == ""
