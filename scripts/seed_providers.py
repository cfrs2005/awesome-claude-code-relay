#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性迁移脚本：把旧 README 表格中的服务商迁移为 providers/*.json。

- 剥离所有 aff/invite/ref/ic 推广参数，只保留干净官网地址
- 星级推荐全部废弃，verification.status 统一置为 unverified（历史从未做过真实验证）
- 迁移产生的 added_at 统一记为迁移日

运行: python3 scripts/seed_providers.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "providers"
MIGRATED_AT = "2026-11-04"

# (id, name, type, website, api_base, notes)
# website 为去掉推广参数后的干净地址；api_base 仅录入有公开依据的端点
PROVIDERS = [
    ("bigmodel",     "智谱 BigModel",  "commercial", "https://bigmodel.cn/",             "https://open.bigmodel.cn/api/anthropic", "官方 Anthropic 兼容端点"),
    ("duckcoding",   "Duckcoding",     "commercial", "https://duckcoding.com",           "https://jp.duckcoding.com",              None),
    ("cubence",      "Cubence",        "commercial", "https://cubence.com",              None, None),
    ("foxcode",      "FoxCode",        "commercial", "https://foxcode.rjj.cc",           None, None),
    ("code-cli",     "CodeCli",        "commercial", "https://www.code-cli.cn",          None, None),
    ("easychat",     "EasyChat",       "commercial", "https://easychat.site",            None, "旧 README 官网域名存在拼写问题，已修正"),
    ("ikuncode",     "Ikuncode",       "commercial", "https://www.ikuncode.cc",          None, None),
    ("galaxycode",   "GalaxyCode",     "commercial", "https://nf.video",                 None, None),
    ("sssaicode",    "SSSAiCode",      "commercial", "https://www.sssaicode.com",        None, None),
    ("mikucode",     "MikuCode",       "commercial", "https://mikucode.xyz",             None, None),
    ("jikeai",       "JikeAI",         "commercial", "https://magic666.top",             None, None),
    ("teapotrouter", "TeapotRouter",   "commercial", "https://teapotrouter.com",         None, "历史为『待评估』，从未验证"),
    ("twinkle",      "Twinkle Model",  "commercial", "https://big-model.smart-agi.com",  None, "历史为『待评估』，从未验证"),
    ("aicodemirror", "AICodeMirror",   "commercial", "https://www.aicodemirror.com",     None, None),
    ("privnode",     "Privnode",       "commercial", "https://privnode.com",             None, None),
    ("uucode",       "Uucode",         "commercial", "https://www.uucode.org",           None, None),
    ("aimz",         "AIMZ",           "commercial", "https://mzlone.top",               None, None),
    ("88code",       "88code",         "commercial", "https://www.88code.org",           None, None),
    ("xyai",         "Xyai",           "commercial", "https://new.xychatai.com",         None, None),
    ("packycode",    "PackyCode",      "commercial", "https://www.packyapi.com",         None, None),
    ("runanytime",   "Runanytime",     "commercial", "https://runanytime.hxi.me",        None, None),
    ("yescode",      "YesCode",        "commercial", "https://co.yes.vg",                None, None),
    ("elysiver",     "Elysiver",       "commercial", "https://elysiver.h-e.top",         None, None),
    ("anyrouter",    "Anyrouter",      "community",  "https://anyrouter.top",            None, "社区公益项目"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for pid, name, ptype, website, api_base, notes in PROVIDERS:
        entry = {
            "id": pid,
            "name": name,
            "type": ptype,
            "website": website,
            "api_base": api_base,
            "models_claimed": [],
            "payment": [],
            "price_note": "",
            "notes": notes or "",
            "added_at": MIGRATED_AT,
            "verification": {
                "status": "unverified",
                "last_verified_at": None,
                "engine_version": None,
                "report_url": None,
            },
        }
        path = OUT / f"{pid}.json"
        if path.exists():
            print(f"skip existing {path.name}")
            continue
        path.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        n += 1
    print(f"written {n} provider files into {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
