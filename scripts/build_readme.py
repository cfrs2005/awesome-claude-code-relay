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
    "endpoint_unreachable": 2,
    "auth_rejected": 2,
    "unverified": 3,
    "model_not_found": 4,
    "protocol_incompatible": 4,
    "behavior_anomaly": 5,
    "identity_suspect": 6,
}
STATUS_LABEL = {
    "basic_passed": "✅ 基础验证通过",
    "pending": "⏳ 验证中",
    "inconclusive": "❔ 证据不足",
    "evidence_insufficient": "❔ 证据不足",
    "unverified": "– 未验证",
    "endpoint_unreachable": "⛔ 端点不可达",
    "auth_rejected": "⛔ 鉴权被拒",
    "model_not_found": "⚠️ 声明模型不存在",
    "protocol_incompatible": "⚠️ 协议不兼容",
    "behavior_anomaly": "⚠️ 行为异常",
    "identity_suspect": "🚨 身份存疑",
}
TYPE_LABEL = {"commercial": "商业", "community": "公益"}
# 家族标注：本目录默认 claude，其他家族必须明示，避免读者误用
FAMILY_LABEL = {
    "claude": "Claude",
    "openai": "OpenAI",
    "gemini": "Gemini",
    "other": "其他",
}
FAMILY_NOTE = {
    "openai": "⚠️ 非 Claude",
    "gemini": "⚠️ 非 Claude",
    "other": "⚠️ 非 Claude",
}

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
        fam_md = FAMILY_LABEL.get(fam, fam)
        if fam != "claude":
            fam_md = f"{fam_md} {FAMILY_NOTE.get(fam, '')}".strip()
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
    readme_path.write_text(text, encoding="utf-8")
    print(f"README 目录表已更新（{len(rows)} 个服务商）")


if __name__ == "__main__":
    main()
