#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录索引生成：Hub 首页的「目录」那一半的数据来源。"""
import importlib.util
import json

from helpers import ROOT

import contracts


def _load():
    spec = importlib.util.spec_from_file_location(
        "bpi", ROOT / "scripts" / "build_providers_index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_provider_has_a_row():
    doc = _load().build()
    on_disk = [p for p in (ROOT / "providers").glob("*.json") if p.name != "schema.json"]
    assert doc["count"] == len(on_disk)
    assert len(doc["items"]) == len(on_disk)


def test_rows_carry_render_fields():
    doc = _load().build()
    for row in doc["items"]:
        assert row["id"] and row["name"]
        assert row["status"] in contracts.VERIFICATION_STATUSES
        assert row["status_label"]
        assert row["tone"] in {"ok", "warn", "err", "info"}
        assert row["family_label"]


def test_sorted_by_verification_status():
    doc = _load().build()
    orders = [contracts.STATUS_ORDER[r["status"]] for r in doc["items"]]
    assert orders == sorted(orders), "目录必须按验证状态排序，通过的在最前"


def test_index_is_json_serialisable():
    doc = _load().build()
    again = json.loads(json.dumps(doc, ensure_ascii=False))
    assert again["count"] == doc["count"]
