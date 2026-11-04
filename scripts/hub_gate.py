#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hub 门禁判定：providers-check 调用。输入 register API 的 JSON。

规则:
  - 未注册 / 非新收录（requires_verification=false）→ 放行
  - 注册且要求验证 → 必须结果 verified=true（verdict=basic_passed 且端点一致）
退出码 0=放行 1=拦截
"""
import json
import sys

VERDICT_ZH = {
    "basic_passed": "基础验证通过",
    "behavior_anomaly": "行为异常",
    "identity_suspect": "身份存疑",
    "evidence_insufficient": "证据不足",
    "inconclusive": "证据不足",
}


def main():
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    if not d.get("registered"):
        print("Hub: 未注册（非新收录流程）→ 跳过门禁")
        return 0
    if not d.get("requires_verification"):
        print("Hub: 条目更新，无需强制验证 → 跳过门禁")
        return 0
    r = d.get("result") or {}
    if r.get("verified"):
        print(f"Hub: ✅ 验证通过（{r.get('verdict')}）")
        return 0
    reasons = []
    if r.get("status") != "completed":
        reasons.append("尚未完成验证：请 PR 作者到 Hub 登录并提交临时 Key、运行验证")
    else:
        reasons.append(f"验证结论: {VERDICT_ZH.get(r.get('verdict'), r.get('verdict'))}")
        if r.get("base_mismatch"):
            reasons.append(f"实测端点 {r.get('tested_base')} 与 PR 声明的 api_base 不一致，请先更新 PR")
    print("Hub: ❌ " + "；".join(reasons))
    print("提示: 维护者可打 mq-manual 标签转人工审查（放弃自动合并）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
