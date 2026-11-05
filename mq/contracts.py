#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQ 契约层：结论枚举、中文文案、配色语义、可合并集合、家族词表、目录状态。

为什么有这个文件
----------------
这些表原先散落在 6 个地方，各自硬编码一份：

    mq/mq.py                 VERDICT_LABEL / VERIFIED_VERDICTS / FAMILY_ALIAS
    scripts/check_mq_report  VERDICT_ZH / MERGEABLE / FAMILY_ALIAS
    scripts/render_report    VERDICT_ZH / PILL_ZH / VERDICT_TONE
    scripts/build_readme     STATUS_ORDER / STATUS_LABEL
    scripts/update_verif.    ALLOWED
    mq/hub/app.py            tone / "== basic_passed"
    providers/schema.json    status enum

于是漂移一定会发生，而且发生过：README badge 落后一个大版本、门禁评论缺两个
state 分支、两处 tone 映射对同一个 verdict 给出相反的颜色。

约定
----
- 本文件只用标准库，任何一层（引擎之外的脚本、Hub、测试）都可以直接 import。
- **`mq/mq.py` 故意不 import 本文件**：它要能作为一个单文件被 `curl` 下来直接跑。
  它保留自己的内嵌副本，由 `tests/test_contracts.py` 强制两边逐键相等。
- 改任何一个枚举，都必须同步 `providers/schema.json`；测试会比对。
"""
from __future__ import annotations

REPO_SLUG = "cfrs2005/awesome-claude-code-relay"

# 引擎版本锚点。分发 URL 指向 tag 而不是 main，否则用户拿到的是浮动 HEAD，
# 报告里写着 engine=0.2.0 但行为可能是任何一次提交。
ENGINE_TAG = "v0.2.0"
MIN_ENGINE_VERSION = "0.2.0"
ENGINE_URL = f"https://raw.githubusercontent.com/{REPO_SLUG}/{ENGINE_TAG}/mq/mq.py"

# ---------------------------------------------------------------- verdict ---

# 结论 → 完整中文名（报告标题、评论正文用）
VERDICT_LABEL = {
    "basic_passed": "基础验证通过",
    "endpoint_unreachable": "端点不可达",
    "auth_rejected": "鉴权被拒",
    "model_not_found": "声明模型不存在",
    "protocol_incompatible": "协议不兼容",
    "behavior_anomaly": "行为异常",
    "identity_suspect": "身份存疑",
    "evidence_insufficient": "证据不足",
}

# 结论 → 短标签（列表徽章用，受布局宽度约束）
VERDICT_PILL = {
    "basic_passed": "通过",
    "endpoint_unreachable": "不可达",
    "auth_rejected": "鉴权失败",
    "model_not_found": "声明不实",
    "protocol_incompatible": "协议不兼容",
    "behavior_anomaly": "行为异常",
    "identity_suspect": "身份存疑",
    "evidence_insufficient": "证据不足",
}

# 结论 → 视觉语义。四个 tone 是全局唯一的一套配色语义（ok / warn / err / info）。
# 判据是「用户该不该因此放弃这个端点」：
#   err  = 端点本身有问题（不可达、声明不实、协议不对、行为异常、身份存疑）
#   warn = 这次测试没做成，但锅不一定是端点的（Key 无效）
#   info = 信息不足，不下判断
VERDICT_TONE = {
    "basic_passed": "ok",
    "endpoint_unreachable": "err",
    "auth_rejected": "warn",
    "model_not_found": "err",
    "protocol_incompatible": "err",
    "behavior_anomaly": "err",
    "identity_suspect": "err",
    "evidence_insufficient": "info",
}

# 门禁放行的唯一结论集合。改这里 = 改产品规则，必须同时改文档。
MERGEABLE = {"basic_passed"}

# 这些结论说明「本次测试没做成」，应提示重跑而不是给端点定罪。
RETRY = {"endpoint_unreachable", "auth_rejected", "evidence_insufficient"}

# quick 模式为了省钱跳过大半探针，不能作为收录依据。
FULL_ENOUGH_MODES = {"standard", "full"}

# --------------------------------------------------------------- 目录状态 ---

# 与 providers/schema.json 的 verification.status enum 必须完全一致（测试会比对）。
VERIFICATION_STATUSES = (
    "unverified",
    "pending",
    "inconclusive",
    "evidence_insufficient",
    "basic_passed",
    "endpoint_unreachable",
    "auth_rejected",
    "model_not_found",
    "protocol_incompatible",
    "behavior_anomaly",
    "identity_suspect",
)

# 旧报告里的保留值 → 目录现存值。只在这一层做映射，别处不要重复特判。
STATUS_ALIAS = {"evidence_insufficient": "inconclusive"}

# README 排序：通过的最前，未验证的其次，身份存疑的最后。
STATUS_ORDER = {
    "basic_passed": 0,
    "pending": 1,
    "inconclusive": 1,
    "evidence_insufficient": 1,   # 旧报告的保留值，与 inconclusive 同级
    "endpoint_unreachable": 2,
    "auth_rejected": 2,
    "unverified": 3,
    "model_not_found": 4,
    "protocol_incompatible": 4,
    "behavior_anomaly": 5,
    "identity_suspect": 6,
}

# README 表格里的状态文案（带表情，用于扫描式阅读）
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

# 目录状态 → 视觉语义（与 VERDICT_TONE 同一套 ok/warn/err/info）
STATUS_TONE = {
    "basic_passed": "ok",
    "pending": "info",
    "inconclusive": "info",
    "evidence_insufficient": "info",
    "unverified": "info",
    # 测试没做成，锅不一定是端点：给「注意」而不是「有问题」
    "endpoint_unreachable": "warn",
    "auth_rejected": "warn",
    "model_not_found": "err",
    "protocol_incompatible": "err",
    "behavior_anomaly": "err",
    "identity_suspect": "err",
}

# ----------------------------------------------------------------- 家族 ---

# 条目里写的是厂商名（openai / anthropic），引擎按模型 id 前缀归类（gpt / claude）。
FAMILY_ALIAS = {"openai": "gpt", "anthropic": "claude", "google": "gemini"}

FAMILY_ORDER = ("claude", "gpt", "gemini", "glm", "qwen", "deepseek", "kimi",
                "moonshot", "llama", "mistral", "grok", "doubao", "ernie")

FAMILY_ZH = {
    "claude": "Claude", "gpt": "OpenAI / GPT", "gemini": "Gemini", "glm": "GLM",
    "qwen": "Qwen", "deepseek": "DeepSeek", "kimi": "Kimi", "moonshot": "Moonshot",
    "llama": "Llama", "mistral": "Mistral", "grok": "Grok", "doubao": "Doubao",
    "ernie": "ERNIE", "other": "其他",
}

# 条目 `family` 字段用的是厂商名（schema enum: claude/openai/gemini/other），
# 与按模型 id 前缀归类的家族词表是两套，README 表格按前者显示。
ENTRY_FAMILY_LABEL = {"claude": "Claude", "openai": "OpenAI",
                      "gemini": "Gemini", "other": "其他"}

# 非 Claude 家族必须在目录里明示，避免读者误以为检的是 Claude
ENTRY_FAMILY_NOTE = {"openai": "⚠️ 非 Claude", "gemini": "⚠️ 非 Claude",
                     "other": "⚠️ 非 Claude"}


def normalize_family(name):
    n = (name or "claude").strip().lower()
    return FAMILY_ALIAS.get(n, n)


def version_lt(a, b):
    """'0.1.0' < '0.2.0'。只处理点分数字，遇到非数字段按字符串比较。"""
    def parts(v):
        out = []
        for seg in str(v or "0").strip().lstrip("v").split("."):
            out.append(int(seg) if seg.isdigit() else seg)
        return out
    pa, pb = parts(a), parts(b)
    for x, y in zip(pa, pb):
        if x == y:
            continue
        if isinstance(x, int) and isinstance(y, int):
            return x < y
        return str(x) < str(y)
    return len(pa) < len(pb)
