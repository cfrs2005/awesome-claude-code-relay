#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 PR 指引评论：告诉提交者怎么在自己机器上跑 MQ、把报告贴回来。

不联网、不需要任何密钥 —— 这是 NQ 式流程的关键：
Key 始终留在提交者自己的机器上，我们不接收、不转发、不存储。

用法:
  python3 scripts/pr_guide.py --base origin/main --head <sha> --out /tmp/guide.md
"""
import argparse
import json
import pathlib
import subprocess
import sys


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--out", default="/tmp/mq_guide.md")
    args = ap.parse_args()

    try:
        out = git("diff", "--name-status", f"{args.base}...{args.head}", "--", "providers/")
    except subprocess.CalledProcessError:
        print("diff 失败，跳过指引")
        pathlib.Path(args.out).write_text("", encoding="utf-8")
        return 0

    paths = [ln.split("\t")[-1] for ln in out.splitlines()
             if ln.strip() and ln.split("\t")[-1].endswith(".json")
             and ln.split("\t")[-1] != "providers/schema.json"]
    if not paths:
        pathlib.Path(args.out).write_text("", encoding="utf-8")
        return 0

    target = paths[0]
    try:
        entry = json.loads(git("show", f"{args.head}:{target}"))
    except Exception:  # noqa: BLE001
        entry = {}

    api_base = (entry.get("api_base") or "").strip()
    family = entry.get("family") or "claude"
    models = entry.get("models_claimed") or []
    model = models[0] if models else "claude-haiku-4-5-20251001"
    shown_base = api_base or "https://api.example.com"

    L = []
    L.append("## 🔬 请在 PR 里贴一份 MQ 测试报告")
    L.append("")
    if family != "claude":
        L.append(f"> ⚠️ 本条目标注为 **{family}** 家族（非 Claude）。报告会按这个期望核验，"
                 f"目录页也会明确标注，读者能看出它不是 Claude 端点。")
    L.append("")
    L.append("本仓库不接收你的 Key，也不在你背后跑测试。**报告由你自己跑、自己贴**，"
             "我们只核验它和这个 PR 声明的是不是同一个端点。")
    L.append("")
    L.append("### 1. 在你自己的机器上跑一次")
    L.append("")
    L.append("```bash")
    L.append("curl -fsSL https://raw.githubusercontent.com/cfrs2005/"
             "awesome-claude-code-relay/main/mq/mq.py -o mq.py")
    L.append(f"python3 mq.py --base-url {shown_base} --key sk-your-key \\")
    L.append(f"  --model {model} --mode standard --expect-family {family} \\")
    L.append("  --json report.json --markdown report.md")
    L.append("```")
    L.append("")
    L.append("只依赖 Python 3.8+ 标准库，Key 不离开你的机器。")
    L.append("")
    L.append("想先看看花多少钱，可以加 `--mode quick` 跑一遍粗测（跳过大半探针）；"
             "但**收录只认 `standard` 及以上**，quick 报告不会被自动合并。")
    if api_base:
        L.append(f"端点和模型取自本 PR 的 `{target}`，如果不对请先改条目再跑。")
    else:
        L.append(f"⚠️ 当前 `{target}` 的 `api_base` 为空，请先填写后再跑。")
    L.append("")
    L.append("### 2. 把 report.md 全文贴到本 PR 的评论里")
    L.append("")
    L.append("报告**第一行**有一段 GitHub 上不可见的机器可读块"
             "（`<!--MQ-REPORT:...-->`）。请整份复制，不要手改 —— "
             "删掉或改动它，Action 就认不出这份报告。")
    L.append("")
    L.append("### 3. 评论 `/mq-done` 触发检查")
    L.append("")
    L.append("### 核验规则（全部确定性，无人工主观判断）")
    L.append("")
    L.append("| 检查项 | 通过条件 |")
    L.append("|---|---|")
    L.append("| 报告存在 | PR 正文或评论里有可解析的 MQ 报告块 |")
    L.append("| 端点一致 | 报告里的 host == 条目 `api_base` 的 host（防「测 A 卖 B」） |")
    L.append("| 报告时效 | 测试时间在 30 天内 |")
    L.append("| 结论合格 | `基础验证通过`；其余结论说明端点本身有问题 |")
    L.append("")
    L.append("四项全过 → **自动合并**，不需要人工审核。不过 → 按提示重测后再贴。")
    L.append("")
    L.append("> 收录 ≠ 推荐，验证通过 ≠ 安全。报告只描述你那次测试观测到什么，"
             "不能证明服务商不留存数据，也不能证明底层模型一定为真。")
    L.append("")
    L.append("维护者认为需要人工判断时，可打 `mq-manual` 标签转人工合并。")

    pathlib.Path(args.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"guide written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
