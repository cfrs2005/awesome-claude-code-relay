#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 MQ 的 report.json 渲染成自包含的 HTML 报告页。

视觉来源：design/relayquality-nodequality/04-report-dark.html
  （Stitch 项目 37768472514992686 / 屏 f2c5b4e7c2ab4a65ad1fe9b2be109a33）

落码原则：设计稿只提供布局与层级，具体色值以本文件的 :root token 为准；
不引入 Tailwind CDN、Google Fonts、图标字体等外部依赖。

用法:
  python3 scripts/render_report.py reports/xxx.json -o reports/xxx.html
  python3 scripts/render_report.py reports/xxx.json            # 同目录同名 .html
"""
import argparse
import base64
import html
import os
import json
import pathlib
import re
import sys

VERDICT_ZH = {
    "basic_passed": "基础验证通过",
    "endpoint_unreachable": "端点不可达",
    "auth_rejected": "鉴权被拒",
    "model_not_found": "声明模型不存在",
    "protocol_incompatible": "协议不兼容",
    "behavior_anomaly": "行为异常",
    "identity_suspect": "身份存疑",
    "evidence_insufficient": "证据不足",
}
PILL_ZH = {
    "basic_passed": "通过",
    "identity_suspect": "身份存疑",
    "model_not_found": "声明不实",
    "behavior_anomaly": "行为异常",
    "protocol_incompatible": "协议不兼容",
    "endpoint_unreachable": "不可达",
    "auth_rejected": "鉴权失败",
    "evidence_insufficient": "证据不足",
}
VERDICT_TONE = {
    "basic_passed": "ok",
    "identity_suspect": "warn",
    "model_not_found": "warn",
    "evidence_insufficient": "warn",
    "behavior_anomaly": "err",
    "protocol_incompatible": "err",
    "endpoint_unreachable": "err",
    "auth_rejected": "err",
}
VERDICT_GLYPH = {"ok": "✓", "warn": "!", "err": "✕", "info": "i"}

GROUP_META = {
    "catalog": ("模型目录", "M4 3h16v4H4zM4 10h10v4H4zM4 17h16v4H4z"),
    "availability": ("端点可用性", "M3 12h4l3-7 4 14 3-7h4"),
    "protocol": ("协议兼容性", "M12 3v18M3 12h18"),
    "identity": ("身份证据", "M12 3l8 4v6c0 5-3.5 7.5-8 8-4.5-.5-8-3-8-8V7z"),
    "stability": ("稳定性与性能", "M4 18V9M9 18V5M14 18v-6M19 18v-9"),
    "other": ("其他检查", "M12 3v18M3 12h18"),
}
GROUP_ORDER = ["catalog", "availability", "protocol", "identity", "stability", "other"]
# 历史报告（v0.1.0）的 check 没有 group 字段，按 id 兜底归组
LEGACY_GROUP = {
    "models": "catalog", "catalog_diff": "catalog", "family_expect": "catalog",
    "basic": "availability", "family_reach": "availability",
    "stream": "protocol", "system": "protocol", "tools": "protocol",
    "thinking": "protocol",
    "consistency": "identity", "official_compare": "identity",
    "count_tokens": "identity", "message_id": "identity", "tool_id": "identity",
    "token_usage": "identity", "sig_roundtrip": "identity", "identity": "identity",
    "stability": "stability",
}
STATUS_TONE = {"PASS": "ok", "WARN": "warn", "FAIL": "err", "INFO": "info"}
STATUS_WORD = {"PASS": "通过", "WARN": "注意", "FAIL": "失败", "INFO": "信息"}
FAMILY_ZH = {"claude": "Claude", "gpt": "OpenAI / GPT", "gemini": "Gemini",
             "glm": "GLM", "qwen": "Qwen", "deepseek": "DeepSeek", "other": "其他"}


def _resolve_font_dir():
    """字体目录：优先环境变量，其次脚本同级 fonts/（部署形态），最后仓库 design/fonts/。"""
    env = os.environ.get("MQ_FONT_DIR")
    if env and pathlib.Path(env).is_dir():
        return pathlib.Path(env)
    here = pathlib.Path(__file__).resolve().parent
    for cand in (here / "fonts", here.parent / "design" / "fonts"):
        if cand.is_dir():
            return cand
    return here / "fonts"


FONT_DIR = _resolve_font_dir()
# 文件名前缀 -> (family, font-weight, style)
FONT_SPEC = {
    "instrument-serif": ("Instrument Serif", "400", "normal"),
    "inter": ("Inter", "100 900", "normal"),      # 可变字重
    "jetbrains-mono": ("JetBrains Mono", "400", "normal"),
}


def font_css():
    """把 design/fonts 下的 woff2 内联成 @font-face，保证报告页零外部请求。

    文件缺失时返回空串——页面会自动回退到 Georgia / 系统无衬线，不会崩。
    """
    if not FONT_DIR.is_dir():
        return ""
    rules = []
    for f in sorted(FONT_DIR.glob("*.woff2")):
        slug = f.name.split("-")[0] if not f.name.startswith("jetbrains") else "jetbrains-mono"
        if f.name.startswith("instrument"):
            slug = "instrument-serif"
        spec = FONT_SPEC.get(slug)
        if not spec:
            continue
        family, weight, style = spec
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        rules.append(
            f'@font-face{{font-family:"{family}";font-style:{style};'
            f'font-weight:{weight};font-display:swap;'
            f'src:url(data:font/woff2;base64,{b64}) format("woff2")}}')
    return "".join(rules)


def esc(v):
    return html.escape("" if v is None else str(v))


def _dict_to_text(m):
    """把 detail 里的 Python 字典字面量改成人类可读形式：{'gpt': 5} -> gpt ×5"""
    pairs = re.findall(r"'([\w\-]+)'\s*:\s*(\d+)", m.group(1))
    if not pairs:
        return m.group(0)
    return " · ".join(f"{k} ×{n}" for k, n in pairs)


def fmt(v):
    """报告正文格式化：字典字面量转文字，反引号转 <code>，其余转义。"""
    s = "" if v is None else str(v)
    s = re.sub(r"\{([^{}]*)\}", _dict_to_text, s)
    s = re.sub(r"`([^`]+)`", lambda m: "\x00" + m.group(1) + "\x01", s)
    s = html.escape(s)
    return s.replace("\x00", "<code>").replace("\x01", "</code>")


CSS = """
:root{
  /* 色彩系统 */
  --paper:#F4F1EA;      /* 主背景 暖奶油白 */
  --surface:#EAE5DC;    /* 次背景 / 容器 浅亚麻灰（比底色深） */
  --ink:#1C1B1A;        /* 近黑墨色，不用纯黑 */
  --ink-2:#5C5A56;      /* 深岩灰 */
  --ink-3:#857F74;      /* 三级文字（由次文本推导） */
  --clay:#D97757;       /* 品牌强调 珊瑚橙 */
  --moss:#4A6B5D;       /* 辅助强调 复古墨绿 */
  --rust:#A6472F;       /* 失败（clay 深阶） */
  --line:#D6D0C4;       /* 1px 柔和描边 */

  /* 字体 */
  --serif:"Instrument Serif","Playfair Display",Georgia,"Songti SC",
          "SimSun",serif;
  --sans:Inter,"Plus Jakarta Sans",-apple-system,BlinkMacSystemFont,
         "Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;

  --r:8px;              /* 统一小圆角，最大 8px */
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--paper);color:var(--ink);
  font:14px/1.75 var(--sans);-webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility}
.wrap{max-width:1000px;margin:0 auto;padding:0 40px}
a{color:inherit;text-decoration:none}

.topbar{height:72px}
.topbar .wrap{height:100%;display:flex;align-items:center;gap:18px}
.brand{font:400 17px/1 var(--serif);letter-spacing:.01em;display:flex;
  align-items:center;gap:9px}
.brand::before{content:"";width:6px;height:6px;border-radius:50%;
  background:var(--clay)}
.topbar .nav{margin-left:auto;font-size:12.5px;color:var(--ink-2)}
.topbar .host{font:12px/1 var(--mono);color:var(--ink-3)}

.verdict{display:grid;grid-template-columns:1fr 250px;gap:56px;align-items:start;
  padding:32px 0 40px;border-bottom:1px solid var(--line)}
.pill{display:inline-block;font-size:11.5px;line-height:1;letter-spacing:.03em;
  padding:6px 10px;border-radius:4px;background:var(--surface);color:var(--ink-2);
  border:1px solid var(--line);margin-bottom:18px}
.pill.warn{border-color:#E4C4B5;color:#A9532F;background:#F2E3D9}
.pill.ok{border-color:#BFCFC6;color:#3E5A4D;background:#E4EAE3}
.pill.err{border-color:#E0BCAF;color:var(--rust);background:#F1DED6}
h1{font:400 34px/1.2 var(--serif);margin:0 0 14px;letter-spacing:-.01em;
  word-break:break-all}
.concl{margin:0;color:var(--ink-2);font-size:13.5px;line-height:1.85;max-width:58ch}

.ratio{text-align:right;color:var(--ink-2);font-size:12.5px;line-height:1.5}
.ratio b{font:400 30px/1 var(--serif);color:var(--ink);margin-right:3px}
.bar{display:flex;height:3px;overflow:hidden;gap:2px;background:var(--line);
  margin:14px 0 12px}
.bar span{display:block;height:100%}
.bar .ok{background:var(--moss)} .bar .warn{background:var(--clay)}
.bar .err{background:var(--rust)} .bar .info{background:#C9C3B6}
.lg{display:flex;gap:14px;justify-content:flex-end;flex-wrap:wrap;
  font:11px/1 var(--mono);color:var(--ink-3)}
.lg i{font-style:normal;color:var(--ink-2)}

.meta{display:grid;grid-template-columns:repeat(4,1fr);
  padding:22px 0 26px;border-bottom:1px solid var(--line)}
.meta > div{padding-left:20px;border-left:1px solid var(--line);min-width:0}
.meta > div:first-child{padding-left:0;border-left:0}
.meta .k{font-size:11px;color:var(--ink-3);margin-bottom:6px;letter-spacing:.02em}
.meta .v{font:12.5px/1.6 var(--mono);color:var(--ink);word-break:break-all}

.group{padding:36px 0 6px}
.gh{display:flex;align-items:baseline;gap:14px;padding-bottom:14px;
  border-bottom:1px solid var(--line)}
.gh h2{font:400 18px/1.4 var(--serif);margin:0;letter-spacing:.005em}
.gh .cnt{margin-left:auto;font:11px/1 var(--mono);color:var(--ink-3)}

.row{display:grid;grid-template-columns:24px 14px 1fr 180px;gap:12px;
  align-items:start;padding:18px 0;border-bottom:1px solid #E2DCD1}
.rows .row:last-child{border-bottom:0}
.idx{font:11.5px/2.1 var(--mono);color:#A29B8E}
.dot{width:6px;height:6px;border-radius:50%;margin-top:10px}
.dot.ok{background:var(--moss)} .dot.warn{background:var(--clay)}
.dot.err{background:var(--rust)} .dot.info{background:#C9C3B6}
.nm{font-weight:500;font-size:14px;line-height:1.65;letter-spacing:.005em}
.ds{color:var(--ink-2);font-size:13px;line-height:1.85;margin-top:5px}
.ds code,.concl code,.repro .note code{font:12px/1 var(--mono);color:var(--ink);
  background:#E5DFD3;padding:2px 5px;border-radius:3px}
.rt{text-align:right}
.sw{font-size:11.5px;line-height:1.4;letter-spacing:.02em}
.sw.ok{color:var(--moss)} .sw.warn{color:var(--clay)}
.sw.err{color:var(--rust)} .sw.info{color:var(--ink-3)}
.mt{font:11px/1.75 var(--mono);color:var(--ink-3);margin-top:5px;word-break:break-all}

.repro{margin-top:44px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r);padding:20px 22px}
.repro .h{display:flex;align-items:baseline;gap:14px;margin-bottom:14px}
.repro .h b{font:400 16px/1.4 var(--serif);font-weight:400}
.repro .h .t{margin-left:auto;font:11px/1 var(--mono);color:var(--ink-3)}
.repro pre{margin:0;font:12px/1.9 var(--mono);color:var(--ink-2);
  white-space:pre-wrap;word-break:break-all}
.repro .note{margin-top:14px;font-size:12px;color:var(--ink-3);line-height:1.8}

details{margin-top:36px;border-top:1px solid var(--line);padding-top:16px}
summary{cursor:pointer;font-size:12.5px;color:var(--ink-2);list-style:none;
  display:flex;align-items:center;gap:9px}
summary::-webkit-details-marker{display:none}
summary::before{content:"\25B8";color:var(--ink-3);font-size:10px}
details[open] summary::before{content:"\25BE"}
summary .f{margin-left:auto;font:11px/1 var(--mono);color:var(--ink-3)}
pre.ev{margin:14px 0 0;font:11.5px/1.85 var(--mono);color:var(--ink-2);
  white-space:pre-wrap;word-break:break-all}

footer{margin:48px 0 56px;padding-top:18px;border-top:1px solid var(--line);
  display:flex;justify-content:space-between;gap:32px;
  font-size:11.5px;color:var(--ink-3);line-height:1.9}
footer .r{text-align:right;font-family:var(--mono)}

@media(max-width:820px){
  .wrap{padding:0 24px}
  .verdict{grid-template-columns:1fr;gap:24px}
  .ratio{text-align:left}
  .lg{justify-content:flex-start}
  .meta{grid-template-columns:repeat(2,1fr);row-gap:18px}
  .meta > div:nth-child(3){padding-left:0;border-left:0}
  .row{grid-template-columns:20px 12px 1fr}
  .rt{grid-column:3;text-align:left}
  footer{display:block}
  footer .r{text-align:left;margin-top:10px}
}
"""


def icon(path):
    return f'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="{path}"/></svg>'


def build(doc):
    meta = doc.get("meta") or {}
    verdict = (doc.get("verdict") or {}).get("label", "")
    detail = (doc.get("verdict") or {}).get("detail", "")
    tone = VERDICT_TONE.get(verdict, "info")
    catalog = doc.get("catalog") or {}
    fams = catalog.get("families") or {}
    checks = doc.get("checks") or []

    fam_txt = " · ".join(f"{FAMILY_ZH.get(k, k)} ×{v}" for k, v in fams.items()) or "未知"
    expect = meta.get("expect_family") or "claude"
    mode = meta.get("mode") or "standard"
    host = meta.get("host") or "—"

    counts = {s: sum(1 for c in checks if c.get("status") == s)
              for s in ("PASS", "WARN", "FAIL", "INFO")}
    total = sum(counts.values()) or 1
    n_pass = counts["PASS"]
    segs = "".join(
        f'<span class="{t}" style="width:{counts[s] / total * 100:.2f}%"></span>'
        for s, t in (("PASS", "ok"), ("WARN", "warn"), ("FAIL", "err"), ("INFO", "info"))
        if counts[s])

    O = []
    O.append(f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MQ 验证报告 — {esc(host)}</title>
<style>{font_css()}{CSS}</style></head><body>

<header class="topbar"><div class="wrap">
  <span class="brand">RelayQuality</span>
  <span class="nav">验证说明</span>
  <span class="host">{esc(host)}</span>
</div></header>

<main class="wrap">

<section class="verdict">
  <div>
    <span class="pill {tone}">{esc(PILL_ZH.get(verdict, verdict))}</span>
    <h1>{esc(host)}</h1>
    <p class="concl">{fmt(detail)}</p>
  </div>
  <div class="ratio">
    <div><b>{n_pass}</b> / {total} 项通过</div>
    <div class="bar">{segs}</div>
    <div class="lg">
      <span>通过 <i>{counts['PASS']}</i></span>
      <span>注意 <i>{counts['WARN']}</i></span>
      <span>失败 <i>{counts['FAIL']}</i></span>
      <span>信息 <i>{counts['INFO']}</i></span>
    </div>
  </div>
</section>

<section class="meta">
  <div><div class="k">声明模型</div><div class="v">{esc(meta.get('requested_model') or '—')}</div></div>
  <div><div class="k">实测模型</div><div class="v">{esc(meta.get('model') or '—')}</div></div>
  <div><div class="k">目录构成</div><div class="v">{esc(fam_txt)}</div></div>
  <div><div class="k">期望家族</div><div class="v">{esc("不限" if expect == "any" else FAMILY_ZH.get(expect, expect))}</div></div>
</section>
""")

    idx = 0
    def group_of(c):
        return c.get("group") or LEGACY_GROUP.get(c.get("id"), "other")

    for gid in GROUP_ORDER:
        items = [c for c in checks if group_of(c) == gid]
        if not items:
            continue
        gname, _ = GROUP_META[gid]
        gp = sum(1 for c in items if c.get("status") == "PASS")
        gf = sum(1 for c in items if c.get("status") == "FAIL")
        summary = f"{len(items)} 项 · {gp} 通过"
        if gf:
            summary += f" · {gf} 失败"
        O.append(f'<section class="group"><div class="gh"><h2>{gname}</h2>'
                 f'<span class="cnt">{summary}</span></div><div class="rows">\n')
        for c in items:
            idx += 1
            st = c.get("status")
            t = STATUS_TONE.get(st, "info")
            mk = " · ".join(f"{k}={v}" for k, v in (c.get("metrics") or {}).items()
                            if v is not None)
            O.append(
                f'<div class="row">'
                f'<span class="idx">{idx:02d}</span>'
                f'<span class="dot {t}"></span>'
                f'<div><div class="nm">{esc(c.get("title"))}</div>'
                f'<div class="ds">{fmt(c.get("detail"))}</div></div>'
                f'<div class="rt"><div class="sw {t}">{STATUS_WORD.get(st, st)}</div>'
                + (f'<div class="mt">{fmt(mk)}</div>' if mk else "")
                + '</div></div>\n'
            )
        O.append("</div></section>\n")

    repro_base = (meta.get("base_url") or "").rstrip("/")
    if repro_base.endswith("/v1"):
        repro_base = repro_base[:-3]
    repro_model = meta.get("requested_model") or meta.get("model") or "<模型>"
    repro_cmd = (
        "curl -fsSL https://raw.githubusercontent.com/cfrs2005/"
        "awesome-claude-code-relay/main/mq/mq.py -o mq.py\n"
        f"python3 mq.py --base-url {repro_base} --key sk-your-key \\\n"
        f"  --model {repro_model} --mode {mode}"
        + ("" if expect == "any" else f" --expect-family {expect}")
    )
    O.append(
        '<section class="repro">'
        '<div class="h"><b>本地复现</b>'
        '<span class="t">同一套探针 · 不依赖本页</span></div>'
        f'<pre>{esc(repro_cmd)}</pre>'
        '<div class="note">Key 只留在你自己的机器上，本页与任何服务端都不接收。'
        '要用官方 Key 做签名回验，加 <code>--official-base-url</code> 与 '
        '<code>--official-key</code>。</div></section>\n')

    ev = [e for c in checks for e in (c.get("evidence") or []) if e]
    if ev:
        O.append('<details><summary>原始证据（已脱敏）'
                 f'<span class="f">{len(ev)} 条 · {idx} 项检查</span></summary>'
                 f'<pre class="ev">{esc(chr(10).join(ev[:40]))}</pre></details>\n')

    O.append(f"""
<footer>
  <div>收录 ≠ 推荐，验证通过 ≠ 安全。本报告只描述 {esc(meta.get('ts'))} 这一次探针观测到的结果，
    不能证明服务商不留存、不转卖请求数据，也不能证明底层模型来自官方。</div>
  <div class="r">引擎 {esc(doc.get('engine'))} · {esc(mode)} 模式<br>
    {idx} 项检查</div>
</footer>
</main></body></html>""")
    return "".join(O)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    src = pathlib.Path(args.json_file)
    doc = json.loads(src.read_text(encoding="utf-8"))
    out = pathlib.Path(args.out) if args.out else src.with_suffix(".html")
    out.write_text(build(doc), encoding="utf-8")
    print(f"rendered: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
