#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Providers PR 确定性校验（自动合并的唯一依据，LLM 结论仅供参考）。

检查项:
  1. 变更路径白名单：只允许 providers/<id>.json（README 等其他文件 => 不自动合并）
  2. JSON Schema 校验（providers/schema.json）
  3. 推广参数扫描：aff/invite/ref/ic 等 => 拒绝；code/channel/from 等 => 警告
  4. id 重复检查（head 树内 + 与 main 现有条目比对）
  5. URL 基本安全检查（https、非 localhost/私网 IP）

用法（CI 内）:
  python3 scripts/check_providers.py --base origin/main --head <pr_head_sha>

输出: 机器可读 JSON（stdout 末行 RESULT: {...}），并写 GitHub Step Summary。
退出码 0 = 可自动合并, 1 = 校验失败。
"""
import argparse
import ipaddress
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.parse

try:
    import jsonschema
except ImportError:
    print("error: 需要 jsonschema（pip install jsonschema）", file=sys.stderr)
    sys.exit(2)

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROVIDERS_DIR = "providers"
PATH_RE = re.compile(r"^providers/[a-z0-9][a-z0-9-]{0,32}\.json$")

# 硬拒绝：明确是推广/返利参数
AFF_HARD = re.compile(r"[?&](aff|aff_?id|invite|invite_?code|inviter|ref|referral|ic|share_?code)=[^\s&#]{2,}", re.I)
# 软警告：可能是推广，也可能正常
AFF_SOFT = re.compile(r"[?&](code|channel|from|promo|utm_[a-z]+)=[^\s&#]{2,}", re.I)

BAD_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def changed_files(base, head):
    out = git("diff", "--name-status", f"{base}...{head}")
    files = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status, path = parts[0], parts[-1]
        files.append((status, path))
    return files


def show(path, ref):
    try:
        return git("show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return None


def load_all_ids(ref):
    listing = git("ls-tree", "--name-only", "-r", ref, PROVIDERS_DIR + "/").splitlines()
    ids = {}
    for p in listing:
        if p.endswith(".json") and p != "providers/schema.json":
            raw = show(p, ref)
            if raw is None:
                continue
            try:
                obj = json.loads(raw)
                ids[obj.get("id", pathlib.Path(p).stem)] = p
            except ValueError:
                pass
    return ids


def check_url(url, field, errs, warns):
    u = urllib.parse.urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https":
        errs.append(f"{field}: 非 https（{url}）")
        return
    if not host or host in BAD_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        errs.append(f"{field}: 非法主机（{url}）")
        return
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            errs.append(f"{field}: 私网/保留地址（{url}）")
            return
    except ValueError:
        pass


def scan_aff(obj, path, errs, warns):
    def walk(node, trail):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, trail + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, trail + [str(i)])
        elif isinstance(node, str):
            if AFF_HARD.search(node):
                errs.append(f"{path}: {'.'.join(trail)} 含推广参数（硬拒绝）: {node[:120]}")
            elif AFF_SOFT.search(node):
                warns.append(f"{path}: {'.'.join(trail)} 疑似推广参数（人工确认）: {node[:120]}")

    walk(obj, [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    args = ap.parse_args()

    errs, warns = [], []
    files = changed_files(args.base, args.head)
    provider_changes = [(s, p) for s, p in files if p.startswith(PROVIDERS_DIR + "/") and p != "providers/schema.json"]
    other_changes = [(s, p) for s, p in files if not (p.startswith(PROVIDERS_DIR + "/") or p == "providers/schema.json")]
    schema_changes = [(s, p) for s, p in files if p == "providers/schema.json"]

    if schema_changes:
        warns.append("providers/schema.json 被修改：需维护者确认后才能自动合并")
    if other_changes:
        errs.append("包含 providers/ 之外的变更，超出自动合并白名单: " +
                    ", ".join(p for _, p in other_changes[:5]))
    if not provider_changes:
        errs.append("没有 providers/*.json 变更")

    schema = json.loads((ROOT / "providers" / "schema.json").read_text(encoding="utf-8"))
    base_ids = load_all_ids(args.base)
    head_ids = dict(base_ids)

    for status, path in provider_changes:
        if not PATH_RE.match(path):
            errs.append(f"文件名不符合 providers/<id>.json 规范: {path}")
            continue
        if status == "D":
            head_ids.pop(pathlib.Path(path).stem, None)
            warns.append(f"{path}: 删除条目需维护者确认")
            continue
        raw = show(path, args.head)
        if raw is None:
            errs.append(f"{path}: head 树中读取失败")
            continue
        try:
            obj = json.loads(raw)
        except ValueError as e:
            errs.append(f"{path}: JSON 解析失败: {e}")
            continue
        try:
            jsonschema.validate(obj, schema)
        except jsonschema.ValidationError as e:
            errs.append(f"{path}: Schema 校验失败: {e.message[:200]}")
            continue
        pid = obj["id"]
        fname = pathlib.Path(path).stem
        if pid != fname:
            errs.append(f"{path}: id({pid}) 与文件名({fname})不一致")
        if status == "A" and pid in base_ids:
            errs.append(f"{path}: 新增条目 id 与现有 {base_ids[pid]} 重复")
        head_ids[pid] = path
        for field in ("website", "api_base"):
            v = obj.get(field)
            if isinstance(v, str):
                check_url(v, f"{path}:{field}", errs, warns)
        scan_aff(obj, path, errs, warns)

    result = {
        "ok": not errs,
        "auto_mergeable": not errs and not any("白名单" in e for e in errs) and len(provider_changes) > 0,
        "errors": errs,
        "warnings": warns,
        "provider_changes": [p for _, p in provider_changes],
    }

    summary = ["## Providers Check 结果", ""]
    summary.append("**" + ("✅ 校验通过" if result["ok"] else "❌ 校验未通过") + "**")
    summary.append("")
    if errs:
        summary.append("### 错误（必须修复）")
        summary.extend(f"- ❌ {e}" for e in errs)
    if warns:
        summary.append("### 警告（人工确认）")
        summary.extend(f"- ⚠️ {w}" for w in warns)
    summary_path = pathlib.Path(os_summary := "/dev/null")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        summary_path = pathlib.Path(os.environ["GITHUB_STEP_SUMMARY"])
        summary_path.write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print("RESULT: " + json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
