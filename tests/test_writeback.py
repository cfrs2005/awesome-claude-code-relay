#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回写逻辑测试。

这条链路的失败方式很特殊：**它原来失败时是静默的**——
PR 号没传进去、`gh pr view ""` 返回空、脚本 exit 0，于是 job 绿、状态丢。
所以这里逐个断言退出码的三种语义。
"""
import json
import shutil
import sys

import pytest

from helpers import ROOT, machine_report, machine_text

import writeback


# ----------------------------------------------------------- 纯函数 --------

@pytest.mark.parametrize("inputs,msg,expected", [
    ("23", "", 23),
    ("#23", "", 23),
    (" 23 ", "", 23),
    ("", "feat: add x (#41)", 41),
    ("", "chore: bump version", None),
    ("", "", None),
    ("not-a-number", "fix: y (#7)", 7),
])
def test_resolve_pr_number(inputs, msg, expected):
    assert writeback.resolve_pr_number(inputs, msg) == expected


def test_provider_files_filters_schema_and_non_providers():
    paths = ["providers/a.json", "providers/schema.json", "README.md",
             "providers/sub/b.json", "scripts/x.py"]
    assert writeback.provider_files(paths) == ["providers/a.json",
                                               "providers/sub/b.json"]


def test_pick_latest_prefers_matching_host():
    older_match = machine_report(host="api.demo.example", tested_at="2026-01-01T00:00:00Z")
    newer_other = machine_report(host="api.other.example", tested_at="2026-06-01T00:00:00Z")
    text = machine_text(older_match) + machine_text(newer_other)
    rep, hosts = writeback.pick_latest_report(text, "api.demo.example")
    assert rep["host"] == "api.demo.example"
    assert set(hosts) == {"api.demo.example", "api.other.example"}


def test_pick_latest_falls_back_to_newest():
    a = machine_report(tested_at="2026-01-01T00:00:00Z")
    b = machine_report(tested_at="2026-06-01T00:00:00Z")
    rep, _ = writeback.pick_latest_report(machine_text(a) + machine_text(b))
    assert rep["tested_at"] == "2026-06-01T00:00:00Z"


def test_pick_latest_on_empty_text():
    rep, hosts = writeback.pick_latest_report("nothing here")
    assert rep is None and hosts == []


def test_pick_latest_ignores_corrupt_blocks():
    text = "<!--MQ-REPORT:bm90LWpzb24=-->\n" * 3 + machine_text(machine_report())
    rep, _ = writeback.pick_latest_report(text)
    assert rep is not None and rep["verdict"] == "basic_passed"


# ------------------------------------------------------------- main --------

FAKE_GH = '''#!/bin/bash
a="$*"
case "$a" in
  *"pulls/23 --jq"*)                echo "PR body" ;;
  *"issues/23/comments"*)           cat "$FAKE_DIR/pr_text.txt" ;;
  *"pr view 23"*"files"*)           cat "$FAKE_DIR/files.txt" ;;
  *"pr view 23"*"headRefOid"*)      echo "sha123" ;;
  *"contents/providers/demo.json"*) cat "$FAKE_DIR/entry_b64.txt" ;;
  *) echo "unexpected: $a" >&2; exit 1 ;;
esac
'''


@pytest.fixture
def wb(tmp_path, monkeypatch):
    """搭一个「像部署目录一样」的工作区：providers/ + scripts/ + mq/ + 假 gh。"""
    shutil.copytree(ROOT / "scripts", tmp_path / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "mq").mkdir()
    shutil.copy(ROOT / "mq" / "contracts.py", tmp_path / "mq" / "contracts.py")
    (tmp_path / "providers").mkdir()
    (tmp_path / "providers" / "demo.json").write_text(json.dumps({
        "id": "demo", "name": "Demo", "type": "commercial",
        "website": "https://demo.example", "api_base": "https://api.demo.example",
        "family": "claude", "added_at": "2026-11-01",
        "verification": {"status": "unverified"},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    import base64
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "pr_text.txt").write_text(machine_text(machine_report()), encoding="utf-8")
    (fake / "files.txt").write_text("providers/demo.json\n", encoding="utf-8")
    (fake / "entry_b64.txt").write_text(
        base64.b64encode((tmp_path / "providers" / "demo.json").read_bytes()).decode(),
        encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ['PATH']}")
    monkeypatch.setenv("FAKE_DIR", str(fake))
    return {"dir": tmp_path, "fake": fake}


def _verification(wb):
    return json.loads((wb["dir"] / "providers" / "demo.json").read_text(encoding="utf-8"))["verification"]


def _run(wb, *args):
    import subprocess
    return subprocess.run(
        [sys.executable, str(wb["dir"] / "scripts" / "writeback.py"), *args],
        cwd=wb["dir"], capture_output=True, text=True).returncode


def test_main_writes_status(wb):
    rc = _run(wb, "--repo", "o/r", "--inputs-pr", "23")
    assert rc == 0
    v = _verification(wb)
    assert v["status"] == "basic_passed"
    assert v["engine_version"] == "0.2.0"
    assert v["report_url"].endswith("/pull/23")


def test_main_exit2_when_no_pr_and_not_strict(wb):
    assert _run(wb, "--repo", "o/r", "--commit-msg", "chore: direct push") == 2


def test_main_exit3_when_no_pr_in_strict_mode(wb):
    assert _run(wb, "--repo", "o/r", "--strict") == 3


def test_main_exit2_when_no_provider_change(wb):
    (wb["fake"] / "files.txt").write_text("scripts/x.py\n", encoding="utf-8")
    assert _run(wb, "--repo", "o/r", "--inputs-pr", "23") == 2


def test_main_exit3_when_no_report(wb):
    (wb["fake"] / "pr_text.txt").write_text("只有描述，没有报告", encoding="utf-8")
    assert _run(wb, "--repo", "o/r", "--inputs-pr", "23") == 3
    assert _verification(wb)["status"] == "unverified"


def test_main_maps_legacy_verdict(wb):
    (wb["fake"] / "pr_text.txt").write_text(
        machine_text(machine_report(verdict="evidence_insufficient")), encoding="utf-8")
    assert _run(wb, "--repo", "o/r", "--inputs-pr", "23") == 0
    # 旧报告的保留值要落到 schema 允许的状态上，否则下次校验会炸
    assert _verification(wb)["status"] == "inconclusive"
