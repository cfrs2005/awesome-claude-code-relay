#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染层测试。

重点不是「HTML 长什么样」，而是三件会被改坏的事：
  1. 同一份 report.json 渲染结果必须逐字节稳定（否则没法发现意外的样式漂移）
  2. 任何不可信字段都必须转义（host / 模型名来自服务商，理论上可被注入）
  3. 不引入外部请求（字体自托管、无 CDN、无 JS）——这条是产品的硬约束
"""
import importlib.util
import json
import re

import pytest

from helpers import ROOT

FIXTURE = ROOT / "tests" / "fixtures" / "report_basic_passed.json"
SNAPSHOT = ROOT / "tests" / "snapshots" / "report_basic_passed.html"


@pytest.fixture
def render(tmp_path, monkeypatch):
    """把字体目录指向一个空的真实目录：输出不含 base64 字体，快照才稳定。"""
    empty = tmp_path / "no-fonts"
    empty.mkdir()
    monkeypatch.setenv("MQ_FONT_DIR", str(empty))
    spec = importlib.util.spec_from_file_location(
        "render_report_mod", ROOT / "scripts" / "render_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _doc(**over):
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc.update(over)
    return doc


def test_snapshot_is_stable(render):
    html = render.build(_doc())
    if not SNAPSHOT.is_file():
        pytest.fail(f"缺少快照文件 {SNAPSHOT}；确认改动是有意的之后重新生成")
    assert html == SNAPSHOT.read_text(encoding="utf-8"), (
        "报告页输出与快照不一致。若是有意的样式改动，删除快照后重跑一次以重新生成。")


def test_no_external_requests_and_no_js(render):
    """硬约束：字体自托管、无 CDN、无 JS。普通 <a> 外链不算外部资源。"""
    html = render.build(_doc())
    assert "<script" not in html, "报告页不允许引入 JS"
    assert not re.search(r'\bsrc="https?://', html), "不允许外部资源引用"
    assert "<link" not in html, "不允许外链样式表/字体"
    assert "url(http" not in html
    assert "cdn." not in html
    assert "googleapis" not in html


def test_untrusted_fields_are_escaped(render):
    doc = _doc()
    doc["meta"]["host"] = '<img src=x onerror="alert(1)">'
    doc["meta"]["requested_model"] = "<script>alert(2)</script>"
    doc["checks"][0]["detail"] = "<b>粗体注入</b>"
    html = render.build(doc)
    assert "<img src=x" not in html
    assert "<script>alert(2)" not in html
    assert "&lt;img src=x" in html
    assert "<b>粗体注入</b>" not in html


def test_seven_verdicts_get_their_own_tone(render):
    import contracts
    assert set(contracts.VERDICT_TONE) == set(contracts.VERDICT_LABEL)
    # 身份存疑属于「端点有问题」，必须是 err；鉴权被拒是「测试没做成」，不该是 err
    assert contracts.VERDICT_TONE["identity_suspect"] == "err"
    assert contracts.VERDICT_TONE["auth_rejected"] == "warn"
    assert contracts.VERDICT_TONE["basic_passed"] == "ok"


def test_index_renders_entries_and_escapes(render):
    entries = [{
        "pr": "23", "ts": "2026-11-05T00:00:00Z", "when": "2026-11-05 00:00",
        "host": "api.demo.example", "family": "claude", "mode": "standard",
        "engine": "0.2.0", "verdict": "basic_passed", "tone": "ok",
        "n_pass": 9, "total": 11, "url": "/r/23/2026-11-05T00:00:00Z",
    }, {
        "pr": "<script>x</script>", "ts": "2026-11-05T00:00:00Z",
        "when": "2026-11-05 00:00", "host": "<b>evil</b>", "family": "gpt",
        "mode": "quick", "engine": "0.1.0", "verdict": "identity_suspect",
        "tone": "err", "n_pass": 2, "total": 9, "url": "/r/1/x",
    }]
    html = render.build_index(entries)
    assert "api.demo.example" in html
    assert "<b>evil</b>" not in html
    assert "<script>x</script>" not in html
    assert "<script" not in html


def test_index_empty_state_guides_next_step(render):
    html = render.build_index([])
    assert "还没有任何报告" in html
    assert "mq.py" in html


PROVIDERS = [
    {"id": "a", "name": "A 站", "type": "commercial", "type_label": "商业",
     "website": "https://a.example", "api_base": "https://api.a.example",
     "family": "claude", "family_label": "Claude", "status": "basic_passed",
     "status_label": "✅ 基础验证通过", "tone": "ok", "engine_version": "0.2.0"},
    {"id": "b", "name": "<script>bad</script>", "type": "community",
     "type_label": "公益", "website": "javascript:alert(1)",
     "api_base": "https://api.b.example", "family": "openai",
     "family_label": "OpenAI ⚠️ 非 Claude", "status": "unverified",
     "status_label": "– 未验证", "tone": "info", "engine_version": None},
]


def test_index_renders_directory_half(render):
    """站点必须是「目录 + 报告」两半，只列报告的话读者看不到有哪些站可选。"""
    html = render.build_index([], providers=PROVIDERS)
    assert "服务商目录" in html
    assert "A 站" in html
    assert "✅ 基础验证通过" in html
    assert "收录 ≠ 推荐" in html


def test_directory_escapes_and_blocks_dangerous_schemes(render):
    html = render.build_index([], providers=PROVIDERS)
    assert "<script>bad</script>" not in html
    assert "javascript:alert(1)" not in html, "非 https 的官网链接不应成为 href"


def test_index_without_providers_says_so(render):
    html = render.build_index([])
    assert "目录索引尚未生成" in html


def test_error_page_is_rendered_and_escaped(render):
    html = render.error_page("找不到这份报告", "没有这个时间点",
                             "<script>alert(1)</script>")
    assert "<h3>" not in html, "错误页必须走统一版式，不能是裸 HTML"
    assert "<script>alert(1)" not in html
    assert "返回目录与报告" in html
