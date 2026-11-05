#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验 PR 上贴的 MQ 测试报告（providers-check 调用）。

设计前提（NQ 式）：
  报告由提交者在**自己的机器上**用 MQ 引擎跑出来，贴到 PR 里举证。
  核验只做三件确定性的事，不做主观评审：

    1. 报告存在，且能被 MQ 的机器可读块解析
    2. 报告里测的 host == PR 声明的 api_base 的 host   ← 防「测 A 卖 B」
    3. 报告在有效期内（默认 30 天），且结论不是硬失败

  三项都过 → 自动合并。任何一项不过 → 不合并，并给出重新测一次的明确指引。

  本脚本不相信报告里的任何自述字段（模型名、结论文案都可能被手改），
  只把机器块当作结构化输入；结论仍以块内的 verdict 枚举为准。

用法:
  python3 scripts/check_mq_report.py \
    --text /tmp/pr_text.txt --base origin/main --head pr-head \
    --summary-file /tmp/mq_summary.md

  输出：人读摘要写 --summary-file，stdout 末行 RESULT: {...}
  退出码：0 = 可自动合并　1 = 不可自动合并
"""
import argparse
import base64
import datetime
import json
import pathlib
import re
import subprocess
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "mq"))
from contracts import (  # noqa: E402
    ENGINE_URL, FAMILY_ALIAS, FULL_ENOUGH_MODES, MERGEABLE, MIN_ENGINE_VERSION,
    RETRY, VERDICT_LABEL, version_lt,
)

BLOCK_RE = re.compile(r"<!--MQ-REPORT:([A-Za-z0-9+/=]+)-->")
REQUIRED_KEYS = ("v", "engine", "tested_at", "base_url", "host", "verdict")

# 结论文案、放行集合、重跑集合、家族词表全部来自契约层（mq/contracts.py）。
VERDICT_ZH = VERDICT_LABEL


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def changed_provider(base, head):
    """取本 PR 变更的单个 providers/*.json（仓库规则：一个 PR 只能新增/修改一个条目）。"""
    out = git("diff", "--name-status", f"{base}...{head}", "--", "providers/")
    paths = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line.split("\t")[-1]
        if path == "providers/schema.json" or not path.endswith(".json"):
            continue
        paths.append(path)
    if not paths:
        return None, None
    path = paths[0]
    try:
        entry = json.loads(git("show", f"{head}:{path}"))
    except Exception:  # noqa: BLE001
        return path, None
    return path, entry


def norm_family(name):
    n = (name or "claude").strip().lower()
    return FAMILY_ALIAS.get(n, n)


def reg_domain(host):
    """取可注册域，用于容忍 api. 之类的前缀差异。不追求完整 PSL。"""
    host = (host or "").lower().split(":")[0]
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])


def host_relation(report_host, declared_host):
    a = (report_host or "").lower().split(":")[0]
    b = (declared_host or "").lower().split(":")[0]
    if not a or not b:
        return "none"
    if a == b:
        return "exact"
    if reg_domain(a) == reg_domain(b):
        return "same-domain"
    return "none"


def parse_block(blob):
    try:
        raw = base64.b64decode(blob, validate=True)
        data = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict) or any(k not in data for k in REQUIRED_KEYS):
        return None
    return data


def age_days(ts):
    try:
        dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except Exception:  # noqa: BLE001
        return None
    return (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 86400.0


def describe(rep):
    fams = rep.get("catalog_families") or {}
    fam = "、".join(f"{k}×{v}" for k, v in fams.items()) or "未知"
    return (f"结论 **{VERDICT_ZH.get(rep.get('verdict'), rep.get('verdict'))}**；"
            f"测试 {rep.get('tested_at')}；目录家族 {fam}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True, help="PR 正文 + 所有评论的拼接文本")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--max-age-days", type=float, default=30.0)
    ap.add_argument("--summary-file", help="人读摘要输出路径")
    ap.add_argument("--json-out", help="机器结果输出路径")
    args = ap.parse_args()

    text = pathlib.Path(args.text).read_text(encoding="utf-8", errors="replace")
    path, entry = changed_provider(args.base, args.head)

    declared_family = (entry or {}).get("family") or "claude"
    if path is None:
        # 纯基础设施 PR（workflow / 脚本 / 文档）不涉及收录，MQ 门禁不适用。
        # 少这一条会导致「改门禁的 PR 被门禁自己挡住」。
        res = {"provider_file": None, "declared_family": None, "declared_base": None,
               "declared_host": "", "reports_found": 0, "report": None,
               "host_relation": "none", "age_days": None,
               "state": "not_applicable", "mergeable": True, "reasons": []}
        out = "## MQ 测试报告核验\n\n本 PR 未变更 `providers/*.json`，" \
              "MQ 报告门禁不适用。\n"
        if args.summary_file:
            pathlib.Path(args.summary_file).write_text(out, encoding="utf-8")
        if args.json_out:
            pathlib.Path(args.json_out).write_text(
                json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(out)
        print("RESULT: " + json.dumps({"state": "not_applicable", "passed": True,
                                       "mergeable": True}, ensure_ascii=False))
        return 0

    res = {
        "provider_file": path,
        "declared_family": declared_family,
        "declared_base": (entry or {}).get("api_base"),
        "declared_host": urllib.parse.urlparse((entry or {}).get("api_base") or "").netloc,
        "reports_found": 0,
        "report": None,
        "host_relation": "none",
        "age_days": None,
        "state": "missing",
        "mergeable": False,
        "reasons": [],
    }

    blocks = BLOCK_RE.findall(text)
    parsed = [p for p in (parse_block(b) for b in blocks) if p]
    res["reports_found"] = len(parsed)

    declared_host = res["declared_host"]
    if not declared_host:
        res["state"] = "no_declared_base"
        res["reasons"].append("PR 条目里 `api_base` 为空，无法与报告比对")
    elif not parsed:
        res["state"] = "missing"
        res["reasons"].append("PR 里没有找到 MQ 测试报告（未找到机器可读块）")
    else:
        # 同一 PR 可能贴了多份：优先取域名匹配的、且最新的那一份
        ranked = sorted(
            parsed,
            key=lambda r: (host_relation(r.get("host"), declared_host) == "exact",
                           r.get("tested_at") or ""),
            reverse=True)
        best = ranked[0]
        rel = host_relation(best.get("host"), declared_host)
        res["report"] = best
        res["host_relation"] = rel
        res["age_days"] = age_days(best.get("tested_at"))

        if rel == "none":
            found_hosts = sorted({r.get("host") for r in parsed if r.get("host")})
            res["state"] = "host_mismatch"
            res["reasons"].append(
                f"报告测的是 `{best.get('host')}`，PR 声明的是 `{declared_host}`（防测 A 卖 B）")
            if found_hosts:
                res["reasons"].append("报告中出现的 host：" + "、".join(f"`{h}`" for h in found_hosts))
        elif res["age_days"] is None:
            res["state"] = "bad_timestamp"
            res["reasons"].append("报告时间戳无法解析")
        elif res["age_days"] > args.max_age_days:
            res["state"] = "stale"
            res["reasons"].append(
                f"报告已过期（{res['age_days']:.1f} 天 > {args.max_age_days:g} 天），请重新跑一次")
        elif version_lt(best.get("engine") or "0", MIN_ENGINE_VERSION):
            # 旧引擎没有家族一致性、模式档位这些检查，它的 basic_passed 不能直接当证据。
            # 不校验版本时，一份 v0.1.0 的报告可以绕过 v0.2.0 才加的规则进入目录。
            res["state"] = "engine_too_old"
            res["reasons"].append(
                f"报告由引擎 `{best.get('engine') or '未知'}` 生成，低于最低要求 "
                f"`{MIN_ENGINE_VERSION}`。旧版引擎缺少家族一致性与档位检查，请用当前版本重跑")
        elif norm_family(best.get("expect_family")) != norm_family(declared_family):
            res["state"] = "family_mismatch"
            res["reasons"].append(
                f"报告是按 `{best.get('expect_family')}` 家族测的，"
                f"但条目标注的 family 是 `{declared_family}`。请用 "
                f"`--expect-family {declared_family}` 重跑")
        elif (best.get("mode") or "standard") not in FULL_ENOUGH_MODES:
            res["state"] = "mode_too_small"
            res["reasons"].append(
                f"报告是 `{best.get('mode')}` 模式跑的，跳过了大部分探针，不能作为收录依据。"
                f"请用 `--mode standard`（或 `full`）重跑")
        elif best.get("verdict") in RETRY:
            res["state"] = "retest"
            res["reasons"].append(
                f"这次测试没有做成（{VERDICT_ZH.get(best.get('verdict'))}），结论无法作为证据，请重跑")
        elif best.get("verdict") not in MERGEABLE:
            res["state"] = "failed"
            res["reasons"].append(
                f"报告结论是「{VERDICT_ZH.get(best.get('verdict'), best.get('verdict'))}」，"
                f"说明被测端点本身有问题")
        else:
            res["state"] = "ok"
            res["mergeable"] = True

    res["passed"] = res["mergeable"]

    # ---------------- 人读摘要 ----------------
    L = ["## MQ 测试报告核验", ""]
    if entry is None:
        L.append(f"未能在 PR 中定位 `providers/*.json` 条目（变更路径：`{path}`）。")
    else:
        L.append(f"- PR 声明端点：`{res['declared_base']}`")
        L.append(f"- 条目标注家族：`{res['declared_family']}`")
    if res["report"]:
        L.append(f"- 报告端点：`{res['report'].get('base_url')}`")
        L.append(f"- 报告时间：`{res['report'].get('tested_at')}`"
                 + (f"（{res['age_days']:.1f} 天前）" if res["age_days"] is not None else ""))
        L.append(f"- 报告摘要：{describe(res['report'])}")
        L.append(f"- 引擎版本：`{res['report'].get('engine')}`"
                 f"　报告 ID：`{res['report'].get('report_id')}`")
    L.append("")

    STATE_HEAD = {
        "ok": "✅ **报告核验通过，可自动合并**",
        "missing": "⏳ **等待 MQ 测试报告**",
        "no_declared_base": "❌ **条目缺少 api_base**",
        "host_mismatch": "❌ **报告端点与 PR 声明不一致**",
        "stale": "⏳ **报告已过期**",
        "retest": "⏳ **需要重跑测试**",
        "failed": "❌ **报告结论不通过**",
        "bad_timestamp": "❌ **报告时间戳异常**",
        "mode_too_small": "⏳ **报告档位太低**",
        "family_mismatch": "❌ **报告家族与条目标注不一致**",
        "engine_too_old": "⏳ **引擎版本过低**",
    }
    L.append(STATE_HEAD.get(res["state"], "⚠️ **状态未知**"))
    L.append("")
    for r in res["reasons"]:
        L.append(f"- {r}")

    if res["state"] in ("missing", "stale", "retest", "mode_too_small",
                        "family_mismatch", "engine_too_old"):
        L.append("")
        L.append("在**你自己的机器**上跑一次（Key 不出本机）：")
        L.append("")
        L.append("```bash")
        L.append(f"curl -fsSL {ENGINE_URL} -o mq.py")
        L.append(f"python3 mq.py --base-url {res['declared_base'] or 'https://api.example.com'} "
                 "--key sk-your-key --model <你声明的模型> \\")
        L.append(f"  --mode standard --expect-family {res['declared_family']} "
                 "--json report.json --markdown report.md")
        L.append("```")
        L.append("")
        L.append("然后把 `report.md` 的**全文**贴到本 PR 的评论里（首行有一段不可见的机器可读块，"
                 "请一并保留，不要手改）。")

    summary = "\n".join(L) + "\n"
    if args.summary_file:
        pathlib.Path(args.summary_file).write_text(summary, encoding="utf-8")
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    print(summary)
    print("RESULT: " + json.dumps({k: res[k] for k in
                                   ("state", "passed", "mergeable", "host_relation",
                                    "reports_found", "declared_host")}, ensure_ascii=False))
    return 0 if res["mergeable"] else 1


if __name__ == "__main__":
    sys.exit(main())
