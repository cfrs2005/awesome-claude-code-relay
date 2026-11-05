#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门禁状态机：每种结论都要落到一个「用户能据以行动」的 state 上。

这些用例对着真实的 git 仓库与真实的脚本跑，不打桩——
因为出问题的地方从来不是纯函数，而是「脚本怎么读 PR 变更集」。
"""
import json
import subprocess
import sys


from helpers import ROOT, machine_report, machine_text

SCRIPT = ROOT / "scripts" / "check_mq_report.py"


def run_gate(repo, text, *, base=None, head=None, extra=()):
    text_file = repo["path"] / "pr_text.txt"
    text_file.write_text(text, encoding="utf-8")
    out = repo["path"] / "out.json"
    cmd = [sys.executable, str(SCRIPT),
           "--text", str(text_file),
           "--base", base or repo["base"],
           "--head", head or repo["head"],
           "--json-out", str(out), *extra]
    proc = subprocess.run(cmd, cwd=repo["path"], capture_output=True, text=True)
    res = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    return proc.returncode, res, proc


def test_ok_state_merges(provider_repo):
    repo = provider_repo()
    rc, res, proc = run_gate(repo, machine_text(machine_report()))
    assert res["state"] == "ok", proc.stdout
    assert res["mergeable"] is True
    assert rc == 0


def test_host_mismatch_blocks(provider_repo):
    repo = provider_repo()
    rep = machine_report(host="api.other.example", base_url="https://api.other.example")
    rc, res, proc = run_gate(repo, machine_text(rep))
    assert res["state"] == "host_mismatch", proc.stdout
    assert res["mergeable"] is False
    assert rc == 1


def test_same_registered_domain_is_accepted(provider_repo):
    """api. 前缀差异要容忍，否则每个条目都会被自己的域名卡住。"""
    repo = provider_repo()
    rep = machine_report(host="api.demo.example", base_url="https://api.demo.example")
    rc, res, _ = run_gate(repo, machine_text(rep))
    assert res["host_relation"] == "exact"
    assert res["state"] == "ok"


def test_stale_report_is_rejected(provider_repo):
    repo = provider_repo()
    rc, res, proc = run_gate(repo, machine_text(machine_report(tested_at="2020-01-01T00:00:00Z")))
    assert res["state"] == "stale", proc.stdout
    assert rc == 1


def test_engine_too_old_is_rejected(provider_repo):
    """旧引擎没有家族/档位检查，它的 basic_passed 不能当证据。"""
    repo = provider_repo()
    rc, res, proc = run_gate(repo, machine_text(machine_report(engine="0.1.0")))
    assert res["state"] == "engine_too_old", proc.stdout
    assert rc == 1


def test_family_mismatch_is_rejected(provider_repo):
    repo = provider_repo(family="claude")
    rc, res, proc = run_gate(repo, machine_text(machine_report(expect_family="gpt")))
    assert res["state"] == "family_mismatch", proc.stdout
    assert rc == 1


def test_quick_mode_is_not_enough(provider_repo):
    repo = provider_repo()
    rc, res, proc = run_gate(repo, machine_text(machine_report(mode="quick")))
    assert res["state"] == "mode_too_small", proc.stdout
    assert rc == 1


def test_retest_for_unfinished_run(provider_repo):
    repo = provider_repo()
    rc, res, proc = run_gate(repo, machine_text(machine_report(verdict="auth_rejected")))
    assert res["state"] == "retest", proc.stdout
    assert rc == 1


def test_failed_verdict_is_rejected(provider_repo):
    repo = provider_repo()
    rc, res, proc = run_gate(repo, machine_text(machine_report(verdict="identity_suspect")))
    assert res["state"] == "failed", proc.stdout
    assert rc == 1


def test_missing_report(provider_repo):
    repo = provider_repo()
    rc, res, proc = run_gate(repo, "只写了一个 PR 描述，没有贴报告")
    assert res["state"] == "missing", proc.stdout
    assert rc == 1


def test_entry_without_api_base(provider_repo):
    repo = provider_repo(api_base=None)
    rc, res, proc = run_gate(repo, machine_text(machine_report()))
    assert res["state"] == "no_declared_base", proc.stdout
    assert rc == 1


def test_infra_only_change_is_not_applicable(provider_repo):
    """改 workflow/脚本的 PR 不涉及收录，门禁不适用（否则改门禁会被门禁挡住）。"""
    repo = provider_repo()
    rc, res, proc = run_gate(repo, "", base=repo["base"], head=repo["base"])
    assert res["state"] == "not_applicable", proc.stdout
    assert rc == 0


def test_summary_contains_retest_command(provider_repo):
    """等待/重跑类状态必须直接给出可复制的命令，否则提交者还得回去翻文档。"""
    repo = provider_repo()
    rc, res, proc = run_gate(repo, machine_text(machine_report(mode="quick")))
    assert "curl -fsSL" in proc.stdout
    assert "--expect-family claude" in proc.stdout
