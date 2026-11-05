#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录条目校验：自动合并的唯一依据。

重点是「哪些变更允许被自动合并」这条边界——放宽 schema、挟带非白名单文件，
都必须判失败而不是警告。
"""
import json
import subprocess
import sys

from helpers import ROOT

SCRIPT = ROOT / "scripts" / "check_providers.py"

VALID = {
    "id": "demo",
    "name": "Demo",
    "type": "commercial",
    "website": "https://demo.example",
    "api_base": "https://api.demo.example",
    "family": "claude",
    "added_at": "2026-11-01",
    "verification": {"status": "unverified"},
}


def run_check(repo, base=None, head=None):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", base or repo["base"],
         "--head", head or repo["head"]],
        cwd=repo["path"], capture_output=True, text=True)
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT: ")), "")
    res = json.loads(line[len("RESULT: "):]) if line else {}
    return proc.returncode, res, proc


def test_valid_entry_passes(provider_repo):
    repo = provider_repo()
    rc, res, proc = run_check(repo)
    assert rc == 0, proc.stdout + proc.stderr
    assert res["ok"] and res["auto_mergeable"]


def test_schema_change_is_rejected(provider_repo):
    """放宽 schema 会让后续所有条目绕过校验，绝不能搭条目 PR 的车合并。"""
    schema = json.loads((ROOT / "providers" / "schema.json").read_text(encoding="utf-8"))
    schema["properties"]["name"]["type"] = "number"   # 任意改动
    repo = provider_repo(extra_files={
        "providers/schema.json": json.dumps(schema, ensure_ascii=False, indent=2)})
    rc, res, proc = run_check(repo)
    assert rc == 1, proc.stdout
    assert not res["ok"]
    assert any("schema.json" in e for e in res["errors"])


def test_affiliate_param_is_rejected(provider_repo):
    repo = provider_repo()
    entry_path = repo["path"] / "providers" / "demo.json"
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["website"] = "https://demo.example/?aff=abc123"
    entry_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    _commit(repo)
    rc, res, proc = run_check(repo, head="HEAD")
    assert rc == 1, proc.stdout
    assert any("推广参数" in e for e in res["errors"])


def test_non_whitelisted_path_is_rejected(provider_repo):
    repo = provider_repo(extra_files={"README.md": "# changed\n"})
    rc, res, proc = run_check(repo)
    assert rc == 1, proc.stdout
    assert any("白名单" in e for e in res["errors"])


def test_http_api_base_is_rejected(provider_repo):
    repo = provider_repo(api_base="http://api.demo.example")
    rc, res, proc = run_check(repo)
    assert rc == 1, proc.stdout
    assert any("https" in e for e in res["errors"])


def _commit(repo):
    subprocess.run(["git", "add", "-A"], cwd=repo["path"], check=True)
    subprocess.run(["git", "commit", "-qm", "edit"], cwd=repo["path"], check=True)
    repo["head"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo["path"],
                                  capture_output=True, text=True).stdout.strip()
