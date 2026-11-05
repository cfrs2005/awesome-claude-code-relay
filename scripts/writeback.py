#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并后回写 verification 状态（sync-readme 工作流调用）。

为什么单独成脚本：回写逻辑原来内嵌在 workflow 的 heredoc 里，无法单测，
也无法在 CI 之外复现。它是整条链路最后一环，之前因为 PR 号没有真正传进
子进程，`gh pr view ""` 静默失败，于是「合并成功、状态没回写、job 还是绿的」。

设计原则：**不确认就报错，不猜测就跳过。**
  - 拿到 PR 号 → 回写 → 退 0
  - 确认这件事不需要回写（纯 infra PR、直推 main 无 PR）→ 退 2
  - 该回写但做不到（拿不到 PR 号、API 失败、找不到条目）→ 退 3，让 job 红

用法:
  python3 scripts/writeback.py --repo owner/repo --inputs-pr 23
  python3 scripts/writeback.py --repo owner/repo --commit-msg "feat: add x (#23)"
  python3 scripts/writeback.py --repo owner/repo --inputs-pr 23 --strict   # 手动触发
"""
import argparse
import base64
import json
import os
import pathlib
import re
import subprocess
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "mq"))
from check_mq_report import BLOCK_RE, host_relation, parse_block  # noqa: E402
from contracts import STATUS_ALIAS  # noqa: E402

EXIT_OK = 0        # 已回写
EXIT_NOOP = 2      # 确认无需回写
EXIT_FAIL = 3      # 应当回写但做不到

PR_IN_MSG_RE = re.compile(r"#(\d+)")
SCHEMA_FILE = "providers/schema.json"


def resolve_pr_number(inputs_pr="", commit_msg=""):
    """把「手动输入」和「合并提交信息」统一成 PR 号，拿不到返回 None。

    纯函数，便于单测。手动输入优先——它的语义是「我明确要补跑这个 PR」。
    """
    raw = (inputs_pr or "").strip().lstrip("#")
    if raw.isdigit():
        return int(raw)
    m = PR_IN_MSG_RE.search(commit_msg or "")
    return int(m.group(1)) if m else None


def provider_files(paths):
    """从变更文件里挑出 provider 条目（排除 schema 与任何非 providers/ 路径）。"""
    out = []
    for p in paths or []:
        p = (p or "").strip()
        if not p.startswith("providers/") or not p.endswith(".json"):
            continue
        if p == SCHEMA_FILE:
            continue
        out.append(p)
    return out


def pick_latest_report(text, declared_host=""):
    """从 PR 正文+评论里挑最能代表该端点的那份报告。

    排序依据与门禁一致：域名精确匹配优先，其次 tested_at 最新。
    返回 (report | None, 报告里出现过的 host 列表)。
    """
    parsed = [p for p in (parse_block(b) for b in BLOCK_RE.findall(text or "")) if p]
    hosts = sorted({p.get("host") for p in parsed if p.get("host")})
    if not parsed:
        return None, hosts
    ranked = sorted(
        parsed,
        key=lambda r: (host_relation(r.get("host"), declared_host) == "exact",
                       r.get("tested_at") or ""),
        reverse=True)
    return ranked[0], hosts


def gh(*args, check=True):
    """调 gh，失败时把 stderr 抛出来，不吞。"""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} 失败：{proc.stderr.strip()}")
    return proc


def fetch_pr_text(repo, pr):
    """PR 正文 + 全部评论。两者都可能贴报告，凭证只看内容不看来源。"""
    body = gh("api", f"repos/{repo}/pulls/{pr}", "--jq", '.body // ""').stdout
    comments = gh("api", "--paginate", f"repos/{repo}/issues/{pr}/comments",
                  "--jq", '.[].body').stdout
    return body + "\n" + comments


def changed_files(repo, pr):
    out = gh("pr", "view", str(pr), "--repo", repo,
             "--json", "files", "--jq", ".files[].path").stdout
    return out.split()


def pr_head_sha(repo, pr):
    return gh("pr", "view", str(pr), "--repo", repo,
              "--json", "headRefOid", "--jq", ".headRefOid").stdout.strip()


def read_entry(repo, ref, path):
    """读 PR head 版本里的条目，用来拿 api_base 做 host 匹配。

    读不到不算失败：host 匹配只是把「最相关的那份报告」排在前面，
    没有它依然能按 tested_at 取最新一份。
    """
    try:
        blob = gh("api", f"repos/{repo}/contents/{path}?ref={ref}",
                  "--jq", ".content").stdout
        return json.loads(base64.b64decode(blob.replace("\n", "")).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def summarize(lines):
    """写到 GITHUB_STEP_SUMMARY，让 Actions 页面上直接看见结论。"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        pathlib.Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/repo")
    ap.add_argument("--inputs-pr", default="", help="手动触发时填的 PR 号")
    ap.add_argument("--commit-msg", default="", help="合并提交信息，从中提取 #N")
    ap.add_argument("--strict", action="store_true",
                    help="手动触发模式：拿不到 PR 号视为失败，而不是跳过")
    args = ap.parse_args()

    pr = resolve_pr_number(args.inputs_pr, args.commit_msg)
    if pr is None:
        msg = ("手动触发必须填 PR 号" if args.strict
               else "提交信息里没有 PR 号，也不是手动触发：判定为无 PR 直推，无需回写")
        summarize([f"## 验证回写已跳过", "", f"- {msg}"])
        print(msg, file=sys.stderr if args.strict else sys.stdout)
        return EXIT_FAIL if args.strict else EXIT_NOOP

    try:
        text = fetch_pr_text(args.repo, pr)
        files = changed_files(args.repo, pr)
        head_sha = pr_head_sha(args.repo, pr)
    except Exception as e:  # noqa: BLE001
        summarize(["## 验证回写失败", "", f"- PR #{pr}：{e}"])
        print(f"PR #{pr} 回写失败：{e}", file=sys.stderr)
        return EXIT_FAIL

    targets = provider_files(files)
    if not targets:
        print(f"PR #{pr} 未变更 providers/*.json，无需回写")
        summarize([f"## 验证回写已跳过", "", f"- PR #{pr} 未变更 `providers/*.json`"])
        return EXIT_NOOP
    if len(targets) > 1:
        print(f"PR #{pr} 变更了多个条目：{', '.join(targets)}；按规则只处理第一个",
              file=sys.stderr)
    target = targets[0]

    entry = read_entry(args.repo, head_sha, target)
    declared_host = urlparse((entry or {}).get("api_base") or "").netloc

    report, hosts = pick_latest_report(text, declared_host)
    if report is None:
        msg = f"PR #{pr} 里没有可解析的 MQ 报告，条目 {target} 保持原状态"
        print(msg, file=sys.stderr)
        summarize(["## 验证回写失败", "",
                   f"- {msg}",
                   f"- 报告机器可读块数量：0"])
        return EXIT_FAIL

    status = STATUS_ALIAS.get(report.get("verdict"), report.get("verdict"))
    pr_url = f"https://github.com/{args.repo}/pull/{pr}"
    proc = subprocess.run(
        [sys.executable, "scripts/update_verification.py", target,
         "--status", status,
         "--engine", report.get("engine") or "",
         "--report-url", pr_url],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"回写 {target} 失败：{proc.stderr.strip()}", file=sys.stderr)
        summarize(["## 验证回写失败", "", f"- `update_verification.py` 退出 {proc.returncode}",
                   f"- {proc.stderr.strip()}"])
        return EXIT_FAIL

    line = (f"回写 {target} → **{status}**"
            f"（报告 {report.get('report_id')} / {report.get('tested_at')} / "
            f"引擎 {report.get('engine')}）")
    print(line)
    summarize(["## 验证回写完成", "", f"- PR #{pr}", f"- 条目 `{target}`",
               f"- 状态 `{status}`",
               f"- 报告 `{report.get('report_id')}` @ {report.get('tested_at')}",
               f"- 引擎 `{report.get('engine')}`",
               f"- 报告内出现过的 host：{'、'.join(hosts) or '—'}"])
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
