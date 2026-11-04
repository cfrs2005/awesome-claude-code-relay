#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 providers/*.json 重新生成 README.md 中的服务商目录表（providers:start/end 标记之间）。
运行: python3 scripts/build_readme.py [README.md]
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROVIDERS = ROOT / "providers"

STATUS_ORDER = {
    "basic_passed": 0,
    "pending": 1,
    "inconclusive": 1,
    "unverified": 2,
    "behavior_anomaly": 3,
    "identity_suspect": 4,
}
STATUS_LABEL = {
    "basic_passed": "✅ 基础验证通过",
    "pending": "⏳ 验证中",
    "inconclusive": "❔ 证据不足",
    "unverified": "– 未验证",
    "behavior_anomaly": "⚠️ 行为异常",
    "identity_suspect": "🚨 身份存疑",
}
TYPE_LABEL = {"commercial": "商业", "community": "公益"}

START, END = "<!-- providers:start -->", "<!-- providers:end -->"


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
        "| 验证状态 | 服务商 | 类型 | 官网 | API 端点（Anthropic 兼容） |",
        "|---|--------|:---:|------|------------------------------|",
    ]
    for _, _, obj in rows:
        v = obj.get("verification", {})
        status = STATUS_LABEL.get(v.get("status", "unverified"), v.get("status"))
        site = obj.get("website") or ""
        base = obj.get("api_base") or "—"
        site_md = f"[{site.replace('https://', '')}]({site})" if site else "—"
        lines.append(f"| {status} | {obj['name']} | {TYPE_LABEL.get(obj.get('type'), obj.get('type'))} "
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
    readme_path.write_text(text, encoding="utf-8")
    print(f"README 目录表已更新（{len(rows)} 个服务商）")


if __name__ == "__main__":
    main()
