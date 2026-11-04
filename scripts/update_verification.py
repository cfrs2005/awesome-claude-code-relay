#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQ 验证完成后回写 provider 状态。
用法: python3 scripts/update_verification.py providers/<id>.json --status basic_passed \
        [--report-url URL] [--engine 0.1.0]
"""
import argparse
import datetime
import json
import pathlib
import sys

ALLOWED = {"unverified", "pending", "basic_passed", "behavior_anomaly", "identity_suspect", "inconclusive"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--status", required=True, choices=sorted(ALLOWED))
    ap.add_argument("--report-url", default=None)
    ap.add_argument("--engine", default=None)
    args = ap.parse_args()

    p = pathlib.Path(args.file)
    obj = json.loads(p.read_text(encoding="utf-8"))
    obj["verification"] = {
        "status": args.status,
        "last_verified_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine_version": args.engine,
        "report_url": args.report_url if args.report_url and args.report_url.startswith("https://") else None,
    }
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated {p}: {args.status}")


if __name__ == "__main__":
    main()
