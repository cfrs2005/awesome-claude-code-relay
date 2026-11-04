#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
register-verify 工作流调用：从 PR 变更提取待测条目，注册到 MQ Hub，
并生成给提交者的指引评论（写入 --out 文件，由 workflow 决定是否发布）。

用法:
  MQ_HUB_TOKEN=xxx python3 scripts/register_hub.py \
    --hub-url https://mq.80aj.com --repo owner/repo --pr 12 \
    --base origin/main --head <sha> --out /tmp/hub_comment.md
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub-url", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--author", default="")
    ap.add_argument("--out", default="/tmp/hub_comment.md")
    args = ap.parse_args()

    hub = args.hub_url.rstrip("/")
    token = os.environ.get("MQ_HUB_TOKEN", "")
    if not token or hub in ("", "https://"):
        print("MQ_HUB_URL / MQ_HUB_TOKEN 未配置，跳过注册")
        pathlib.Path(args.out).write_text("", encoding="utf-8")
        return 0

    diff = git("diff", "--name-status", f"{args.base}...{args.head}", "--", "providers/")
    added, modified = [], []
    for line in diff.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status, path = parts[0], parts[-1]
        if path == "providers/schema.json" or not path.endswith(".json"):
            continue
        if status.startswith("A"):
            added.append(path)
        elif status.startswith("M"):
            modified.append(path)

    target = None
    kind = None
    if added:
        target, kind = added[0], "new"
    elif modified:
        target, kind = modified[0], "update"
    else:
        print("无 providers/*.json 条目变更，跳过")
        pathlib.Path(args.out).write_text("", encoding="utf-8")
        return 0

    try:
        entry = json.loads(git("show", f"{args.head}:{target}"))
    except Exception as e:  # noqa: BLE001
        print(f"解析 {target} 失败: {e}")
        entry = {}
    pid = entry.get("id") or pathlib.Path(target).stem
    api_base = entry.get("api_base") or ""
    models = entry.get("models_claimed") or []

    payload = {
        "repo": args.repo, "pr": args.pr, "provider_id": pid,
        "provider_file": pathlib.Path(target).name,
        "api_base": api_base or None,
        "model": models[0] if models else "claude-haiku-4-5-20251001",
        "author": args.author, "kind": kind,
        "requires_verification": kind == "new",
    }
    req = urllib.request.Request(hub + "/api/prs", data=json.dumps(payload).encode(),
                                 headers={"x-hub-token": token, "content-type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print("registered:", resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"::error::Hub 注册失败 HTTP {e.code}: {e.read().decode()[:200]}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"::error::Hub 不可达: {e}")
        return 1

    lines = []
    if kind == "new":
        lines.append("## 🔬 MQ 官方验证（新收录必做）")
        lines.append("")
        lines.append(f"本 PR 已注册到 MQ Hub，验证入口：**{hub}/**")
        lines.append("")
        lines.append("1. 用 **GitHub 登录** Hub（必须是本 PR 作者本人）")
        lines.append("2. 提交**一次性临时 Key**（低额度、短有效期；仅存 Hub 内存，20 分钟过期，触发即焚）")
        lines.append("3. 在 Hub 点击 **运行验证** —— 报告会自动回贴到本 PR")
        if not api_base:
            lines.append("")
            lines.append(f"> ⚠️ 当前 PR 的 `api_base` 为空，请先在 `{target}` 中填写 Anthropic 兼容端点后再到 Hub 提测。")
        lines.append("")
        lines.append("验证通过 + 全部检查通过后 PR 自动合并；验证不通过请修复后重试，或请维护者打 `mq-manual` 标签转人工。")
    else:
        lines.append("## 🔬 MQ Hub")
        lines.append("")
        lines.append(f"条目变更已同步到 MQ Hub（{hub}/）。如需重新验证，可在 Hub 重新提交临时 Key 触发。")
    pathlib.Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"comment written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
