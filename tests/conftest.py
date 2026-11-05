#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pytest 公共夹具。辅助函数见 tests/helpers.py。"""
import json
import pathlib
import sys
import threading

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
for p in (ROOT / "mq", ROOT / "scripts", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import mock_relay  # noqa: E402  须在上面的 sys.path 之后
from helpers import git  # noqa: E402


@pytest.fixture
def relay(monkeypatch):
    """启动一个 mock 端点，返回 base_url。同一个测试里只会有一个。

    每次请求都读环境变量，所以测试里可以直接 monkeypatch.setenv 改变目录形态。
    """
    servers = []

    def _start(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, str(v))
        srv, port = mock_relay.create_server(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return f"http://127.0.0.1:{port}"

    yield _start
    for srv in servers:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def provider_repo(tmp_path):
    """造一个 base...head 的 git 仓库，用于测门禁（check_mq_report / check_providers）。"""
    def _make(api_base="https://api.demo.example", family="claude",
              entry_id="demo", status="unverified", extra_files=None):
        repo = tmp_path / f"repo-{entry_id}"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "t@example.com")
        git(repo, "config", "user.name", "t")
        (repo / "providers").mkdir()
        (repo / "providers" / "schema.json").write_text(
            (ROOT / "providers" / "schema.json").read_text(encoding="utf-8"),
            encoding="utf-8")
        (repo / "README.md").write_text("# base\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")
        base = git(repo, "rev-parse", "HEAD").strip()

        entry = {
            "id": entry_id,
            "name": "Demo",
            "type": "commercial",
            "website": "https://demo.example",
            "added_at": "2026-11-01",
            "family": family,
            "verification": {"status": status},
        }
        if api_base is not None:
            entry["api_base"] = api_base
        (repo / "providers" / f"{entry_id}.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        for name, content in (extra_files or {}).items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "add demo")
        head = git(repo, "rev-parse", "HEAD").strip()
        return {"path": repo, "base": base, "head": head, "entry": entry}

    return _make
