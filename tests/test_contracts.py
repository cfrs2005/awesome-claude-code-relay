#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""契约一致性测试：同一份枚举不允许在多个文件里各写一遍。

这些用例的价值不在「跑通」，而在**漂移会被立刻抓住**：
改 mq.py 的一个结论文案而不改 contracts.py，这里就红。
"""
import importlib.util
import json
import re

from helpers import ROOT

import contracts


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ENGINE = _load("mq_engine", "mq/mq.py")
CHECK = _load("check_mq_report_mod", "scripts/check_mq_report.py")
RENDER = _load("render_report_mod", "scripts/render_report.py")


def test_engine_verdict_labels_match_contracts():
    assert ENGINE.VERDICT_LABEL == contracts.VERDICT_LABEL


def test_engine_mergeable_set_matches_contracts():
    assert ENGINE.VERIFIED_VERDICTS == contracts.MERGEABLE


def test_engine_family_tables_match_contracts():
    assert ENGINE.FAMILY_ALIAS == contracts.FAMILY_ALIAS
    assert tuple(ENGINE.FAMILY_ORDER) == tuple(contracts.FAMILY_ORDER)


def test_gate_tables_match_contracts():
    assert CHECK.MERGEABLE == contracts.MERGEABLE
    assert CHECK.RETRY == contracts.RETRY
    assert CHECK.FULL_ENOUGH_MODES == contracts.FULL_ENOUGH_MODES
    assert CHECK.VERDICT_ZH == contracts.VERDICT_LABEL


def test_render_tables_match_contracts():
    # 渲染层不再自带副本；这里是回归防线，防止有人又拷一份回去
    assert RENDER.VERDICT_ZH is contracts.VERDICT_LABEL
    assert RENDER.PILL_ZH is contracts.VERDICT_PILL
    assert RENDER.VERDICT_TONE is contracts.VERDICT_TONE
    assert RENDER.FAMILY_ZH is contracts.FAMILY_ZH


def test_schema_enum_matches_contracts():
    schema = json.loads((ROOT / "providers" / "schema.json").read_text(encoding="utf-8"))
    enum = schema["properties"]["verification"]["properties"]["status"]["enum"]
    assert set(enum) == set(contracts.VERIFICATION_STATUSES), (
        "providers/schema.json 的 status enum 与 mq/contracts.py 不一致")


def test_every_status_has_label_and_order():
    for st in contracts.VERIFICATION_STATUSES:
        assert st in contracts.STATUS_LABEL, st
        assert st in contracts.STATUS_ORDER, st


def test_every_verdict_has_label_pill_and_tone():
    for v in contracts.VERDICT_LABEL:
        assert v in contracts.VERDICT_PILL, v
        assert v in contracts.VERDICT_TONE, v
        assert contracts.VERDICT_TONE[v] in {"ok", "warn", "err", "info"}, v


def test_mergeable_subset_of_verdicts():
    assert contracts.MERGEABLE <= set(contracts.VERDICT_LABEL)
    assert contracts.RETRY <= set(contracts.VERDICT_LABEL)


def test_version_lt():
    assert contracts.version_lt("0.1.0", "0.2.0")
    assert contracts.version_lt("v0.1.9", "v0.2.0")
    assert not contracts.version_lt("0.2.0", "0.2.0")
    assert not contracts.version_lt("0.10.0", "0.9.0")
    assert contracts.version_lt("0", contracts.MIN_ENGINE_VERSION)


def test_engine_tag_matches_min_version():
    """分发锚点与最低版本必须是同一个版本线，否则用户按指引跑出来还是旧引擎。"""
    assert contracts.ENGINE_TAG.lstrip("v") == contracts.MIN_ENGINE_VERSION


def test_no_one_distributes_from_main():
    """曾散落 6 处的 raw/main URL 已收敛到 contracts.ENGINE_URL（tag 化）。"""
    pattern = re.compile(r"raw\.githubusercontent\.com/[^\s\"']+/main/mq/mq\.py")
    offenders = []
    for path in list((ROOT / "scripts").glob("*.py")) + [ROOT / "mq" / "mq.py"]:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)
    assert not offenders, f"仍从 main 分发引擎：{offenders}"


def test_engine_url_is_tag_pinned():
    assert "/main/" not in contracts.ENGINE_URL
    assert contracts.ENGINE_TAG in contracts.ENGINE_URL
