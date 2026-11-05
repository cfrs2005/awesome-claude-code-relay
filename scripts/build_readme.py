#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 providers/*.json 重新生成 README.md 中的服务商目录表（providers:start/end 标记之间），
顺带同步顶部两个 badge（服务商数量、MQ 引擎版本）—— 它们曾经长期漂移：
条目涨到 31 个、引擎到了 0.2.0，badge 还写着 30 和 v0.1.0。

运行: python3 scripts/build_readme.py [README.md]
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROVIDERS = ROOT / "providers"
ENGINE = ROOT / "mq" / "mq.py"

sys.path.insert(0, str(ROOT / "mq"))
from contracts import (  # noqa: E402
    ENTRY_FAMILY_LABEL, ENTRY_FAMILY_NOTE, STATUS_LABEL, STATUS_ORDER,
)

TYPE_LABEL = {"commercial": "商业", "community": "公益"}

START, END = "<!-- providers:start -->", "<!-- providers:end -->"

BADGE_PROVIDERS = re.compile(r"(badge/服务商-)\d+(-blue)")
BADGE_ENGINE = re.compile(r"(badge/MQ%20引擎-v)[0-9][^)-]*-(purple)")


def engine_version():
    try:
        m = re.search(r'^MQ_VERSION\s*=\s*"([^"]+)"',
                      ENGINE.read_text(encoding="utf-8"), re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def sync_badges(text, count):
    """把 badge 上的数字对齐到真实数据，避免又一处静默漂移。"""
    text = BADGE_PROVIDERS.sub(lambda m: f"{m.group(1)}{count}{m.group(2)}", text)
    ver = engine_version()
    if ver:
        text = BADGE_ENGINE.sub(lambda m: f"{m.group(1)}{ver}-{m.group(2)}", text)
    return text


def main():
    readme_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "README.md"
    rows = []
    for f in sorted(PROVIDERS.glob("*.json")):
        if f.name == "schema.json":
            continue
        obj = json.loads(f.read_text(encoding="utf-8"))
        v = obj.get("verification", {})
        rows.append((STATUS_ORDER.get(v.get("status", "unverified"), 9), obj["name"], obj))
    rows.sort(key=lambda r: (r[0], r[1].lower()))

    lines = [
        "| 验证状态 | 服务商 | 家族 | 类型 | 官网 | API 端点 |",
        "|---|--------|:---:|:---:|------|------------------------------|",
    ]
    for _, _, obj in rows:
        v = obj.get("verification", {})
        status = STATUS_LABEL.get(v.get("status", "unverified"), v.get("status"))
        site = obj.get("website") or ""
        base = obj.get("api_base") or "—"
        site_md = f"[{site.replace('https://', '')}]({site})" if site else "—"
        fam = obj.get("family") or "claude"
        fam_md = ENTRY_FAMILY_LABEL.get(fam, fam)
        if fam != "claude":
            fam_md = f"{fam_md} {ENTRY_FAMILY_NOTE.get(fam, '')}".strip()
        lines.append(f"| {status} | {obj['name']} | {fam_md} "
                     f"| {TYPE_LABEL.get(obj.get('type'), obj.get('type'))} "
                     f"| {site_md} | `{base}` |")

    table = "\n".join(lines)
    text = readme_path.read_text(encoding="utf-8")
    if START in text and END in text:
        before, rest = text.split(START, 1)
        _, after = rest.split(END, 1)
        text = before + START + "\n" + table + "\n" + END + after
    else:
        print(f"warning: 未找到 {START}/{END} 标记，README 未更新", file=sys.stderr)
        sys.exit(1)
    text = sync_badges(text, len(rows))
    readme_path.write_text(text, encoding="utf-8")
    print(f"README 目录表已更新（{len(rows)} 个服务商，引擎 {engine_version() or '?'}）")


if __name__ == "__main__":
    main()
