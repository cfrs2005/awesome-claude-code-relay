#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQ Hub — 中转站官方验证入口（部署于 ntt197, mq.80aj.com）

流程:
  1. GitHub Action (register-verify) 从 PR 提取 api_base，POST /api/prs 注册待测条目
  2. 提交者用 GitHub OAuth 登录 Hub（必须是 PR 作者），提交一次性临时 Key（仅存内存，TTL 20 分钟）
  3. 提交者在 Hub 上触发测试 → 服务端运行 engine/mq.py → 生成脱敏报告
  4. 报告回贴 PR 评论 + verification 状态提交到 PR 分支 → providers-check 全绿 → 自动合并

安全约定:
  - Key 只存在进程内存，触发即消费（一次性），TTL 过期即焚；绝不写盘/写日志
  - 报告由引擎脱敏后落盘 data/reports/
  - 登录身份与 PR 作者强绑定；PR 必须处于 open 状态才允许提交/测试

环境变量见文末 README 或 systemd EnvironmentFile。
"""
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, FileResponse

# ---------------------------------------------------------------- config ---

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8710").rstrip("/")
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
ENGINE_PATH = os.environ.get("ENGINE_PATH", str(Path(__file__).parent.parent / "mq.py"))
PORT = int(os.environ.get("PORT", "8710"))
REPO = os.environ.get("REPO", "cfrs2005/awesome-claude-code-relay")
HUB_TOKEN = os.environ.get("HUB_TOKEN", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-secret-change-me")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # PAT: issues:write + contents:write
DEV_MODE = os.environ.get("DEV_MODE", "") == "1"
ALLOW_ANY_AUTHOR = os.environ.get("ALLOW_ANY_AUTHOR", "") == "1"  # 仅联调: 放开作者绑定校验
KEY_TTL = 20 * 60
RUN_COOLDOWN = 90
RUN_TIMEOUT = 300

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
STORE_PATH = DATA_DIR / "prs.json"

_store_lock = threading.Lock()
_run_locks: dict[str, threading.Lock] = {}
KEYS: dict[str, dict] = {}  # pr -> {key, base, exp} 仅内存

app = FastAPI(title="MQ Hub", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------- store ----

def load_store() -> dict:
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"prs": {}}


def save_store(store: dict) -> None:
    tmp = STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STORE_PATH)


# ---------------------------------------------------------------- github ---

def gh_api(method: str, path: str, token: str = "", body: dict | None = None):
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "user-agent": "mq-hub/0.1",
        "accept": "application/vnd.github+json",
        **({"authorization": f"Bearer {token}"} if token else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            err = {}
        return {"__error__": True, "status": e.code, "message": err.get("message", "")}
    except Exception as e:  # noqa: BLE001
        return {"__error__": True, "status": 0, "message": f"{type(e).__name__}: {e}"[:200]}


def pr_info(repo: str, pr: int) -> dict:
    if DEV_MODE and not GITHUB_TOKEN:
        return {"state": "open", "head": {"ref": f"dev/pr-{pr}"}, "user": {"login": ""}}
    r = gh_api("GET", f"/repos/{repo}/pulls/{pr}", token=GITHUB_TOKEN)
    if r.get("__error__"):
        return {"state": "unknown", "head": {"ref": ""}, "user": {"login": ""}}
    return r


# ---------------------------------------------------------------- session --

def _sign(payload: bytes) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload, hashlib.sha256).hexdigest()[:32]


def make_session(login: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps(
        {"login": login, "exp": int(time.time()) + 7 * 86400}).encode()).decode()
    return body + "." + _sign(body.encode())


def read_session(request: Request) -> str | None:
    raw = request.cookies.get("mq_session", "")
    body, _, sig = raw.rpartition(".")
    if not body or not hmac.compare_digest(sig, _sign(body.encode())):
        return None
    try:
        obj = json.loads(base64.urlsafe_b64decode(body))
    except Exception:
        return None
    if obj.get("exp", 0) < time.time():
        return None
    return obj.get("login")


def current_user(request: Request) -> str | None:
    dev = request.query_params.get("dev_user")
    if DEV_MODE and dev:
        return dev
    return read_session(request)


# ---------------------------------------------------------------- helpers --

def public_result(binding: dict) -> dict:
    r = binding.get("last_result") or {}
    return {
        "status": r.get("status"),
        "verdict": r.get("verdict"),
        "tested_base": r.get("tested_base"),
        "base_mismatch": r.get("base_mismatch"),
        "verified": r.get("status") == "completed" and r.get("verdict") == "basic_passed"
                    and not r.get("base_mismatch"),
        "report_url": r.get("report_url"),
        "finished_at": r.get("finished_at"),
        "engine": r.get("engine"),
    }


def mask_key(k: str) -> str:
    return (k[:6] + "***" + k[-4:]) if len(k) > 12 else "***"


# ---------------------------------------------------------------- engine ---

def run_engine(base_url: str, key: str, model: str, out_dir: Path) -> tuple[dict, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / "report.json", out_dir / "report.md"
    fd, kp = tempfile.mkstemp(suffix=".key")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(key)
        os.chmod(kp, 0o600)
        proc = subprocess.run(  # noqa: S603
            [sys.executable, ENGINE_PATH, "--base-url", base_url, "--key-file", kp,
             "--model", model, "--json", str(jp), "--markdown", str(mp)],
            capture_output=True, text=True, timeout=RUN_TIMEOUT)
        if not jp.exists():
            raise RuntimeError(f"engine failed: {proc.stderr[-800:] or proc.stdout[-800:]}")
        doc = json.loads(jp.read_text(encoding="utf-8"))
        return doc, mp.read_text(encoding="utf-8")
    finally:
        try:
            os.unlink(kp)
        except OSError:
            pass


def commit_verification_to_pr(repo: str, pr: int, provider_file: str,
                              verdict: str, engine: str, report_url: str) -> dict:
    """把 verification 状态提交到 PR 分支（仅在 PAT 已配置时）。"""
    if not GITHUB_TOKEN or DEV_MODE:
        return {"skipped": True}
    info = pr_info(repo, pr)
    branch = (info.get("head") or {}).get("ref") or ""
    if not branch:
        return {"skipped": True, "reason": "no branch"}
    path = f"providers/{provider_file}"
    cur = gh_api("GET", f"/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}",
                 token=GITHUB_TOKEN)
    if cur.get("__error__"):
        return {"skipped": True, "reason": cur.get("message", "get failed")}
    import datetime
    obj = json.loads(base64.b64decode(cur["content"]).decode("utf-8"))
    obj["verification"] = {
        "status": verdict,
        "last_verified_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine_version": engine,
        "report_url": report_url,
    }
    put = gh_api("PUT", f"/repos/{repo}/contents/{urllib.parse.quote(path)}", token=GITHUB_TOKEN, body={
        "message": f"mq: verification -> {verdict} (engine {engine})",
        "content": base64.b64encode(json.dumps(obj, ensure_ascii=False, indent=2).encode()).decode(),
        "sha": cur["sha"],
        "branch": branch,
    })
    return {"committed": not put.get("__error__"), "detail": put.get("message", "")}


def post_pr_comment(repo: str, pr: int, body: str) -> dict:
    if not GITHUB_TOKEN or DEV_MODE:
        return {"skipped": True}
    r = gh_api("POST", f"/repos/{repo}/issues/{pr}/comments", token=GITHUB_TOKEN,
               body={"body": body[:65000]})
    return {"posted": not r.get("__error__"), "detail": r.get("message", "")}


# ---------------------------------------------------------------- api ------

def require_hub_token(request: Request) -> None:
    if not HUB_TOKEN:
        raise HTTPException(500, "HUB_TOKEN 未配置")
    got = request.headers.get("x-hub-token", "")
    if not hmac.compare_digest(got, HUB_TOKEN):
        raise HTTPException(401, "bad hub token")


@app.get("/healthz")
def healthz():
    return {"ok": True, "engine": Path(ENGINE_PATH).exists(),
            "oauth": bool(GITHUB_CLIENT_ID), "token": bool(GITHUB_TOKEN)}


@app.post("/api/prs")
async def api_register_pr(request: Request):
    require_hub_token(request)
    payload = await request.json()
    return register_pr(payload)


def register_pr(payload: dict) -> dict:
    pr = int(payload["pr"])
    with _store_lock:
        store = load_store()
        binding = store["prs"].setdefault(str(pr), {
            "pr": pr, "registered_at": int(time.time())})
        binding.update({
            "repo": payload.get("repo") or REPO,
            "provider_id": payload.get("provider_id"),
            "provider_file": payload.get("provider_file"),
            "api_base": (payload.get("api_base") or "").rstrip("/") or None,
            "model": payload.get("model") or "claude-haiku-4-5-20251001",
            "author": payload.get("author"),
            "kind": payload.get("kind", "new"),
            "requires_verification": bool(payload.get("requires_verification", True)),
            "updated_at": int(time.time()),
        })
        save_store(store)
    return {"ok": True, "pr": pr, "api_base": binding["api_base"]}


@app.get("/api/prs/{pr}")
def api_get_pr(pr: int, request: Request):
    """providers-check 的合并门禁调用（X-Hub-Token），或登录用户查看。"""
    if request.headers.get("x-hub-token") and HUB_TOKEN and hmac.compare_digest(
            request.headers["x-hub-token"], HUB_TOKEN):
        pass
    elif not current_user(request):
        raise HTTPException(401, "login required")
    with _store_lock:
        store = load_store()
    binding = store["prs"].get(str(pr))
    if not binding:
        return {"registered": False, "requires_verification": False, "verified": False}
    return {
        "registered": True,
        "repo": binding["repo"],
        "provider_id": binding["provider_id"],
        "api_base": binding["api_base"],
        "author": binding["author"],
        "kind": binding["kind"],
        "requires_verification": binding["requires_verification"],
        "key_ready": str(pr) in KEYS and KEYS[str(pr)]["exp"] > time.time(),
        "result": public_result(binding),
    }


@app.post("/api/prs/{pr}/key")
async def api_submit_key(pr: int, request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "请先登录")
    with _store_lock:
        store = load_store()
    binding = store["prs"].get(str(pr))
    if not binding:
        raise HTTPException(404, "该 PR 未注册验证（请等待 register-verify 工作流运行）")
    if (binding.get("author") or "").lower() != user.lower() and not ALLOW_ANY_AUTHOR:
        raise HTTPException(403, f"仅 PR 作者 ({binding.get('author')}) 可提交 Key")
    info = pr_info(binding["repo"], pr)
    if info.get("state") != "open":
        raise HTTPException(409, f"PR 当前状态 {info.get('state')}，仅 open 状态可提测")
    if not binding.get("api_base"):
        raise HTTPException(400, "PR 的 api_base 为空，请先在 PR 中填写 Anthropic 兼容端点")

    body = await request.json()
    key = (body.get("key") or "").strip()
    base = (body.get("base_url") or "").strip().rstrip("/")
    if not key.startswith("sk-") and len(key) < 16:
        raise HTTPException(400, "Key 格式可疑（应以 sk- 开头且长度足够）")
    if base and not base.startswith("https://") and "127.0.0.1" not in base:
        raise HTTPException(400, "覆盖端点必须 https")
    KEYS[str(pr)] = {"key": key, "base": base or None, "exp": int(time.time()) + KEY_TTL}
    return {"ok": True, "expires_in": KEY_TTL, "hint": "Key 仅存内存，触发测试后即消费；过期自动焚毁"}


@app.post("/api/prs/{pr}/run")
def api_run(pr: int, request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "请先登录")
    with _store_lock:
        store = load_store()
    binding = store["prs"].get(str(pr))
    if not binding:
        raise HTTPException(404, "该 PR 未注册验证")
    if (binding.get("author") or "").lower() != user.lower() and not ALLOW_ANY_AUTHOR:
        raise HTTPException(403, "仅 PR 作者可触发测试")
    info = pr_info(binding["repo"], pr)
    if info.get("state") != "open":
        raise HTTPException(409, f"PR 当前状态 {info.get('state')}，仅 open 状态可提测")

    lk = _run_locks.setdefault(str(pr), threading.Lock())
    if not lk.acquire(blocking=False):
        raise HTTPException(429, "已有测试在运行中")
    try:
        keyrec = KEYS.pop(str(pr), None)  # 一次性消费
        if not keyrec or keyrec["exp"] < time.time():
            raise HTTPException(400, "没有有效 Key，请先提交（Key 为一次性，测试后需重新提交）")
        last = (binding.get("last_result") or {}).get("finished_at", 0)
        if time.time() - last < RUN_COOLDOWN and not DEV_MODE:
            raise HTTPException(429, f"冷却中，请 {RUN_COOLDOWN}s 后重试")

        tested_base = keyrec["base"] or binding["api_base"]
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        out_dir = REPORTS_DIR / str(pr) / ts
        doc, md = run_engine(tested_base, keyrec["key"], binding.get("model"), out_dir)
        verdict = doc.get("verdict", {}).get("label", "inconclusive")
        engine_v = doc.get("engine", "?")
        report_url = f"{BASE_URL}/reports/{pr}/{ts}.md"
        base_mismatch = bool(tested_base != (binding.get("api_base") or ""))

        result = {
            "status": "completed", "verdict": verdict, "engine": engine_v,
            "tested_base": tested_base, "base_mismatch": base_mismatch,
            "finished_at": int(time.time()), "report_url": report_url,
        }
        with _store_lock:
            store = load_store()
            store["prs"][str(pr)]["last_result"] = result
            store["prs"][str(pr)]["last_run_at"] = int(time.time())
            save_store(store)

        comment = post_pr_comment(binding["repo"], pr, md + (
            f"\n\n---\n- 实测端点: `{tested_base}`" +
            ("\n- ⚠️ 实测端点与 PR 声明的 api_base 不一致，请先更新 PR" if base_mismatch else "") +
            f"\n- 引擎: `{engine_v}` · 报告: {report_url}"))
        commit = commit_verification_to_pr(
            binding["repo"], pr, binding.get("provider_file") or f"{binding.get('provider_id')}.json",
            verdict, engine_v, report_url)
        return {"ok": True, **public_result({**binding, "last_result": result}),
                "github": {"comment": comment, "commit": commit}}
    finally:
        lk.release()


@app.get("/reports/{pr}/{name}")
def get_report(pr: int, name: str):
    safe = Path(name).name
    p = REPORTS_DIR / str(pr) / safe
    if not p.is_file():
        raise HTTPException(404, "report not found")
    return FileResponse(p, media_type="text/markdown" if safe.endswith(".md") else "application/json")


@app.get("/auth/github/callback")
def oauth_callback(request: Request, code: str = "", state: str = ""):
    if not GITHUB_CLIENT_ID:
        return HTMLResponse("<h3>OAuth 未配置</h3><p>请先在服务器配置 GITHUB_CLIENT_ID/SECRET</p>", 503)
    req = urllib.request.Request("https://github.com/login/oauth/access_token", data=urllib.parse.urlencode({
        "client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET,
        "code": code, "redirect_uri": f"{BASE_URL}/auth/github/callback",
    }).encode(), headers={"accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            tok = json.loads(resp.read()).get("access_token", "")
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(f"<h3>OAuth 失败</h3><pre>{type(e).__name__}: {e}</pre>", 502)
    if not tok:
        return HTMLResponse("<h3>OAuth 失败</h3><p>code 无效或已过期</p>", 401)
    req2 = urllib.request.Request("https://api.github.com/user",
                                  headers={"user-agent": "mq-hub/0.1", "authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req2, timeout=20) as resp:
        login = json.loads(resp.read()).get("login", "")
    resp = HTMLResponse("<meta http-equiv='refresh' content='0;/'>登录成功，正在返回…")
    resp.set_cookie("mq_session", make_session(login), httponly=True, samesite="lax",
                    max_age=7 * 86400, secure=BASE_URL.startswith("https"))
    return resp


@app.get("/login/github")
def login_github():
    if not GITHUB_CLIENT_ID:
        return HTMLResponse("<h3>OAuth 未配置</h3>", 503)
    url = ("https://github.com/login/oauth/authorize?client_id=" + GITHUB_CLIENT_ID +
           "&redirect_uri=" + urllib.parse.quote(f"{BASE_URL}/auth/github/callback") +
           "&scope=read%3Auser")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url)


# ---------------------------------------------------------------- page -----

PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MQ Hub — 中转站官方验证入口</title>
<style>
:root{--bg:#0d1117;--fg:#e6edf3;--muted:#8b949e;--acc:#58a6ff;--ok:#3fb950;--warn:#d29922;--err:#f85149;--card:#161b22;--bd:#30363d}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--fg);line-height:1.6}
.wrap{max-width:880px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:1.5em}a{color:var(--acc);text-decoration:none}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:18px 20px;margin:16px 0}
.muted{color:var(--muted);font-size:.9em}
.tag{display:inline-block;padding:1px 10px;border-radius:99px;font-size:.8em;border:1px solid var(--bd)}
.ok{color:var(--ok)}.warn{color:var(--warn)}.err{color:var(--err)}
button{background:#21262d;color:var(--fg);border:1px solid var(--bd);border-radius:6px;padding:8px 16px;cursor:pointer;font-size:.95em}
button:hover{border-color:var(--acc)}button.primary{background:#1f6feb;border-color:#1f6feb}
input{width:100%;background:#0d1117;color:var(--fg);border:1px solid var(--bd);border-radius:6px;padding:9px 12px;font-size:.95em;margin:4px 0 12px}
code{background:#21262d;padding:1px 6px;border-radius:4px;font-size:.88em}
pre{background:#010409;border:1px solid var(--bd);border-radius:8px;padding:14px;overflow:auto;font-size:.85em}
</style></head><body><div class="wrap">
<h1>🔬 MQ Hub <span class="muted">— 中转站官方验证入口</span></h1>
<p class="muted">临时 Key 仅存内存：一次性消费 · {ttl} 分钟过期 · 绝不落盘 · 报告自动回贴 PR · 通过后自动合并。<br>
收录 ≠ 推荐，验证通过 ≠ 安全。请提交<b>低额度、短有效期</b>的专用 Key，测试完成后立即吊销。</p>
<div id="status" class="card">加载中…</div>
<div id="main"></div>
<div class="card muted"><b>流程</b>：PR 提交 providers/*.json → Action 自动注册本站 → PR 作者 GitHub 登录本站 →
提交临时 Key → 点击「运行验证」→ 报告回贴 PR & 更新 verification → 检查通过后自动合并。<br>
<b>注意</b>：实测端点必须与 PR 声明的 <code>api_base</code> 一致，不一致会被拦截。</div>
</div>
<script>
const q = new URLSearchParams(location.search);
async function j(url, opts) { const r = await fetch(url, opts); const d = await r.json().catch(()=>({})); if (!r.ok) throw new Error(d.detail || r.status); return d; }
async function boot() {
  let me = null;
  try { me = await j('/api/me'); } catch (e) {}
  const st = document.getElementById('status');
  if (!me) {
    st.innerHTML = '<b>第一步：GitHub 登录</b>（必须是 PR 作者本人）<br><br><a href="/login/github"><button class="primary">🔐 使用 GitHub 登录</button></a>';
    return;
  }
  st.innerHTML = '<b>已登录：</b><code>' + me.login + '</code> · <span class="muted">仅显示与你相关的待验证 PR</span>';
  const main = document.getElementById('main');
  if (!me.prs.length) {
    main.innerHTML = '<div class="card muted">当前没有绑定到你（' + me.login + '）的待验证 PR。<br>
提交 PR 修改 <code>providers/*.json</code> 后，register-verify 工作流会自动注册到这里。</div>';
    return;
  }
  main.innerHTML = '';
  for (const b of me.prs) {
    const d = document.createElement('div'); d.className = 'card';
    const res = b.result || {}; const verified = res.verified;
    const badge = verified ? '<span class="tag ok">✅ 已通过</span>'
      : (res.status === 'completed' ? '<span class="tag err">❌ ' + (res.verdict||'') + '</span>' : '<span class="tag warn">⏳ 待验证</span>');
    d.innerHTML = `
      <b>#${b.pr} ${b.provider_id||''}</b> ${badge}<br>
      <span class="muted">端点 <code>${b.api_base||'—（PR 未填写 api_base）'}</code> · 模型 <code>${b.model}</code></span>
      ${res.report_url ? '<br><span class="muted">报告：' + res.report_url + '</span>' : ''}
      <hr style="border-color:var(--bd)">
      ${!verified ? `
      <label>临时 API Key（一次性，${Math.round(b.key_ttl/60)} 分钟有效）</label>
      <input id="k-${b.pr}" placeholder="sk-..." autocomplete="off">
      <label class="muted">覆盖端点（可选；留空 = 使用 PR 声明的 api_base；不一致会被拦截）</label>
      <input id="u-${b.pr}" placeholder="https://api.example.com（可选）">
      <button onclick="submitKey(${b.pr})">① 提交 Key</button>
      <button class="primary" onclick="runTest(${b.pr})">② 运行验证</button>` : '<span class="muted">已完成验证，PR 将在全部检查通过后自动合并。</span>'}
      <div id="m-${b.pr}" class="muted" style="margin-top:10px"></div>`;
    main.appendChild(d);
  }
  window.submitKey = async (pr) => {
    const m = document.getElementById('m-'+pr); m.textContent = '提交中…';
    try {
      const key = document.getElementById('k-'+pr).value.trim();
      const base_url = document.getElementById('u-'+pr).value.trim();
      const r = await j(`/api/prs/${pr}/key`, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({key, base_url})});
      m.innerHTML = '<span class="ok">✅ Key 已接收（内存暂存）</span> — ' + r.hint;
    } catch (e) { m.innerHTML = '<span class="err">❌ ' + e.message + '</span>'; }
  };
  window.runTest = async (pr) => {
    const m = document.getElementById('m-'+pr); m.textContent = '⏳ 引擎运行中（约 1-3 分钟），请勿关闭页面…';
    try {
      const r = await j(`/api/prs/${pr}/run`, {method:'POST'});
      m.innerHTML = `<span class="${r.verified?'ok':'err'}">${r.verified?'✅ 验证通过，报告已回贴 PR':'验证完成：'+(r.verdict||'')} — <a href="${r.report_url}">查看报告</a></span>`;
      setTimeout(boot, 1500);
    } catch (e) { m.innerHTML = '<span class="err">❌ ' + e.message + '</span>'; }
  };
}
boot();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE.replace("{ttl}", str(KEY_TTL // 60))


@app.get("/api/me")
def api_me(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "not logged in")
    with _store_lock:
        store = load_store()
    prs = []
    for b in store["prs"].values():
        if (b.get("author") or "").lower() != user.lower() and not DEV_MODE:
            continue
        prs.append({
            "pr": b["pr"], "provider_id": b.get("provider_id"), "api_base": b.get("api_base"),
            "model": b.get("model"), "result": public_result(b),
            "key_ttl": KEY_TTL,
        })
    return {"login": user, "prs": prs}
