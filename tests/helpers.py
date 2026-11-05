#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试辅助函数（不放夹具，夹具在 conftest.py）。

原则：**不花额度、不连外网**。所有网络交互都指向 tests/mock_relay.py。
"""
import base64
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = ROOT / "mq" / "mq.py"


def run_engine(base_url, tmp_path, *extra, key="sk-test-0123456789",
               model="claude-haiku-4-5-20251001", mode="standard"):
    """跑一次真实引擎（子进程），返回 (退出码, report.json, report.md, CompletedProcess)。"""
    tmp_path = pathlib.Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    cmd = [sys.executable, str(ENGINE), "--base-url", base_url, "--key", key,
           "--model", model, "--mode", mode, "--allow-http",
           "--json", str(out_json), "--markdown", str(out_md), *extra]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    doc = json.loads(out_json.read_text(encoding="utf-8")) if out_json.is_file() else None
    md = out_md.read_text(encoding="utf-8") if out_md.is_file() else ""
    return proc.returncode, doc, md, proc


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, check=True).stdout


def machine_text(report, extra=""):
    """把一份机器块渲染成「PR 正文/评论」的样子。"""
    blob = base64.b64encode(json.dumps(report, ensure_ascii=False).encode()).decode()
    return f"{extra}\n<!--MQ-REPORT:{blob}-->\n"


def machine_report(**over):
    """一份最小的、可被门禁解析的报告机器块。键与 mq.py 的 machine_comment 对齐。"""
    rep = {
        "v": 1,
        "engine": "0.2.0",
        "tested_at": "2099-01-01T00:00:00Z",   # 默认永不过期，过期用例自行覆盖
        "base_url": "https://api.demo.example",
        "host": "api.demo.example",
        "declared_model": "claude-haiku-4-5-20251001",
        "tested_model": "claude-haiku-4-5-20251001",
        "model_substituted": False,
        "catalog_families": {"claude": 2},
        "catalog_count": 2,
        "mode": "standard",
        "expect_family": "claude",
        "verdict": "basic_passed",
        "checks": [],
        "report_id": "0123456789abcdef",
    }
    rep.update(over)
    return rep
