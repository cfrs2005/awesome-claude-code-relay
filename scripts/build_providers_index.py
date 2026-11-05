#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 providers/*.json 压成 Hub 首页要用的索引文件（providers-index.json）。

为什么要预生成而不是运行时读仓库：
Hub 部署在服务器上，没有仓库工作副本；运行时去 GitHub API 拉 31 个文件
既有速率限制又会拖慢首页。部署时生成一次，跟着发布包一起走。

用法:
  python3 scripts/build_providers_index.py            # 写到仓库根目录
  python3 scripts/build_providers_index.py -o /tmp/x.json
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mq"))
from contracts import (  # noqa: E402
    ENTRY_FAMILY_LABEL, ENTRY_FAMILY_NOTE, STATUS_LABEL, STATUS_ORDER,
    STATUS_TONE,
)


def build():
    rows = []
    for f in sorted((ROOT / "providers").glob("*.json")):
        if f.name == "schema.json":
            continue
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            print(f"warning: 跳过无法解析的 {f.name}: {e}", file=sys.stderr)
            continue
        status = (obj.get("verification") or {}).get("status") or "unverified"
        family = obj.get("family") or "claude"
        fam_label = ENTRY_FAMILY_LABEL.get(family, family)
        if family != "claude":
            fam_label = f"{fam_label} {ENTRY_FAMILY_NOTE.get(family, '')}".strip()
        rows.append({
            "id": obj.get("id") or f.stem,
            "name": obj.get("name") or f.stem,
            "type": obj.get("type"),
            "type_label": {"commercial": "商业", "community": "公益"}.get(
                obj.get("type"), obj.get("type")),
            "website": obj.get("website"),
            "api_base": obj.get("api_base") or "",
            "family": family,
            "family_label": fam_label,
            "status": status,
            "status_label": STATUS_LABEL.get(status, status),
            "tone": STATUS_TONE.get(status, "info"),
            "last_verified_at": (obj.get("verification") or {}).get("last_verified_at"),
            "engine_version": (obj.get("verification") or {}).get("engine_version"),
        })
    rows.sort(key=lambda r: (STATUS_ORDER.get(r["status"], 9), r["name"].lower()))
    return {"version": 1, "count": len(rows), "items": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=str(ROOT / "providers-index.json"))
    args = ap.parse_args()
    doc = build()
    pathlib.Path(args.out).write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"providers-index.json 已生成：{doc['count']} 个服务商 → {args.out}")


if __name__ == "__main__":
    main()
