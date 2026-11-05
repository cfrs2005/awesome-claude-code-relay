#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引擎端到端：真的起一个 HTTP 端点、真的跑一遍 mq.py。

这里覆盖的是 `mq.py --self-test` 够不到的东西：SSE 解析、错误分类、
机器可读块与门禁解析的往返一致性。全部打到 tests/mock_relay.py，不花额度。
"""
import json

from helpers import ROOT, run_engine

import check_mq_report
import contracts


def _checks(doc):
    return {c["id"]: c for c in doc.get("checks", [])}


def test_engine_version_matches_contracts():
    spec_text = (ROOT / "mq" / "mq.py").read_text(encoding="utf-8")
    assert f'MQ_VERSION = "{contracts.MIN_ENGINE_VERSION}"' in spec_text


def test_standard_run_passes(relay, tmp_path):
    base = relay()
    rc, doc, md, proc = run_engine(base, tmp_path)
    assert rc == 0, proc.stderr
    assert doc is not None, proc.stderr
    assert doc["verdict"]["label"] == "basic_passed", doc["verdict"]
    assert doc["engine"] == contracts.MIN_ENGINE_VERSION


def test_machine_block_roundtrips_through_gate(relay, tmp_path):
    """引擎写出的 <!--MQ-REPORT--> 必须能被门禁原样解回来。

    这是三方契约（引擎生成 / 门禁解析 / 回写消费）最容易漂移的地方，
    之前没有任何一条测试跨过这条边界。
    """
    base = relay()
    rc, doc, md, proc = run_engine(base, tmp_path)
    assert rc == 0, proc.stderr

    blocks = check_mq_report.BLOCK_RE.findall(md)
    assert len(blocks) == 1, "报告首行应当有且只有一段机器可读块"
    parsed = check_mq_report.parse_block(blocks[0])
    assert parsed is not None, "门禁无法解析引擎生成的机器块"
    assert parsed["verdict"] == doc["verdict"]["label"]
    assert parsed["engine"] == doc["engine"]
    # 机器块里的 host 带端口（base_url 的 netloc 原样），门禁比对时两边都会剥端口
    assert parsed["host"].startswith("127.0.0.1")
    for key in ("tested_at", "base_url", "mode", "catalog_families", "report_id"):
        assert key in parsed, f"机器块缺字段 {key}"


def test_openai_catalog_under_claude_expectation_is_identity_suspect(relay, tmp_path):
    base = relay(MOCK_MODELS="gpt-6-luna,gpt-5.6")
    rc, doc, md, proc = run_engine(base, tmp_path)
    assert doc is not None, proc.stderr
    assert doc["verdict"]["label"] == "identity_suspect", doc["verdict"]
    assert "family_expect" in _checks(doc)


def test_bad_key_is_auth_rejected(relay, tmp_path):
    base = relay()
    rc, doc, md, proc = run_engine(base, tmp_path, key="not-a-key")
    assert doc is not None, proc.stderr
    assert doc["verdict"]["label"] == "auth_rejected", doc["verdict"]
    # 门禁对 auth_rejected 的处置是「重跑」，不是给端点定罪
    assert "auth_rejected" in check_mq_report.RETRY


def test_upstream_5xx_is_endpoint_unreachable(relay, tmp_path):
    base = relay(MOCK_HTTP=502)
    rc, doc, md, proc = run_engine(base, tmp_path)
    assert doc is not None, proc.stderr
    assert doc["verdict"]["label"] == "endpoint_unreachable", doc["verdict"]


def test_malformed_sse_is_counted_not_fatal(relay, tmp_path):
    base = relay(MOCK_MALFORMED=1)
    rc, doc, md, proc = run_engine(base, tmp_path)
    assert doc is not None, proc.stderr
    stream = _checks(doc).get("stream")
    assert stream is not None
    assert stream["status"] in ("WARN", "FAIL")
    assert "畸形" in stream["detail"] or "malformed" in json.dumps(stream["metrics"])


def test_base_url_with_v1_suffix_is_normalized(relay, tmp_path):
    base = relay() + "/v1"
    rc, doc, md, proc = run_engine(base, tmp_path)
    assert doc is not None, proc.stderr
    assert doc["verdict"]["label"] == "basic_passed", doc["verdict"]
    assert not doc["meta"]["base_url"].endswith("/v1/messages")


def test_key_never_appears_in_report(relay, tmp_path):
    secret = "sk-should-not-leak-abcdef123456"
    base = relay()
    rc, doc, md, proc = run_engine(base, tmp_path, mode="quick", key=secret)
    assert secret not in md
    assert secret not in json.dumps(doc, ensure_ascii=False)


def test_catalog_flip_against_previous_report_is_flagged(relay, tmp_path, monkeypatch):
    """37 分钟内 claude×11 → gpt×9 的换上游场景，必须在报告里看得见。"""
    base = relay(MOCK_MODELS="claude-haiku-4-5-20251001,claude-sonnet-4-5-20250929")
    rc, doc, md, proc = run_engine(base, tmp_path / "run1", mode="quick")
    assert doc is not None, proc.stderr
    prev = tmp_path / "run1" / "report.json"

    # 换上游：目录家族完全翻转，并带上一份历史报告做对比
    monkeypatch.setenv("MOCK_MODELS", "gpt-6-luna,gpt-5.6")
    rc2, doc2, md2, proc2 = run_engine(
        base, tmp_path / "run2", mode="quick", *("--previous-report", str(prev)))
    assert doc2 is not None, proc2.stderr
    diff = _checks(doc2).get("catalog_diff")
    assert diff is not None, "带 --previous-report 时必须产出目录对比"
    assert diff["status"] in ("WARN", "FAIL")
    assert doc2["verdict"]["label"] == "identity_suspect"
