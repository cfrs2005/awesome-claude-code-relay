#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQ Hub — 中转站官方验证入口（部署于 ntt197, mq.80aj.com）

流程（无需 OAuth App / 无需提交者任何 token）:
  1. GitHub Action (register-verify) 从 PR 提取 api_base，POST /api/prs 注册待测条目
  2. 提交者在 Hub 获取一次性「绑定码」，到 PR 下评论它（GitHub 即身份证明）
  3. Hub 校验评论者 == PR 作者 → 发会话 → 提交一次性临时 Key（仅内存，TTL 20 分钟）
  4. 提交者触发测试 → 服务端运行 engine/mq.py → 报告回贴 PR 评论
  5. 提交者在 PR 评论 /mq-done → providers-check 全绿 → 直接 squash 合并

安全约定:
  - Key 只存在进程内存，触发即消费（一次性），TTL 过期即焚；绝不写盘/写日志
  - 实测端点 = PR 声明端点（注册时由 Action 提取）；覆盖端点提测会被标记并拦截
  - 门禁 verified 为动态计算: verdict=basic_passed 且 tested_base == 当前 PR api_base
"""
import base64
import datetime
import hashlib
import hmac
import json
import os
import secrets as pysecrets
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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

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
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # PAT 或 gh token: issues:write
DEV_MODE = os.environ.get("DEV_MODE", "") == "1"
ALLOW_ANY_AUTHOR = os.environ.get("ALLOW_ANY_AUTHOR", "") == "1"  # 仅联调
KEY_TTL = 20 * 60
BIND_TTL = 15 * 60
RUN_COOLDOWN = 90
RUN_TIMEOUT = 300

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
STORE_PATH = DATA_DIR / "prs.json"

_store_lock = threading.Lock()
_run_locks: dict[str, threading.Lock] = {}
KEYS: dict[str, dict] = {}    # pr -> {key, base, exp} 仅内存
BINDS: dict[str, dict] = {}   # pr -> {code, exp} 仅内存

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
        "user-agent": "mq-hub/0.2",
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
        return {"state": "open", "user": {"login": ""}}
    r = gh_api("GET", f"/repos/{repo}/pulls/{pr}", token=GITHUB_TOKEN)
    if r.get("__error__"):
        return {"state": "unknown"}
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
    """动态计算 verified：verdict 合格 且 实测端点 == 当前声明端点（防测后改 PR）。"""
    r = binding.get("last_result") or {}
    tested = r.get("tested_base") or ""
    declared = (binding.get("api_base") or "").rstrip("/")
    verified = (r.get("status") == "completed" and r.get("verdict") == "basic_passed"
                and bool(tested) and tested.rstrip("/") == declared)
    return {
        "status": r.get("status"),
        "verdict": r.get("verdict"),
        "tested_base": r.get("tested_base"),
        "declared_base": declared or None,
        "base_mismatch": bool(tested) and tested.rstrip("/") != declared,
        "verified": verified,
        "report_url": r.get("report_url"),
        "finished_at": r.get("finished_at"),
        "engine": r.get("engine"),
    }


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


def post_pr_comment(repo: str, pr: int, body: str) -> dict:
    if DEV_MODE or not GITHUB_TOKEN:
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


def get_binding(pr: int) -> dict | None:
    with _store_lock:
        store = load_store()
    return store["prs"].get(str(pr))


@app.get("/healthz")
def healthz():
    return {"ok": True, "engine": Path(ENGINE_PATH).exists(),
            "gh_token": bool(GITHUB_TOKEN), "oauth": bool(GITHUB_CLIENT_ID)}


@app.post("/api/prs")
async def api_register_pr(request: Request):
    require_hub_token(request)
    payload = await request.json()
    pr = int(payload["pr"])
    with _store_lock:
        store = load_store()
        binding = store["prs"].setdefault(str(pr), {"pr": pr, "registered_at": int(time.time())})
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


@app.get("/api/prs")
def api_list_prs():
    """公开列表（信息本就公开于仓库/PR）：不含任何 Key。"""
    with _store_lock:
        store = load_store()
    out = []
    for b in sorted(store["prs"].values(), key=lambda x: -x["pr"]):
        out.append({"pr": b["pr"], "provider_id": b.get("provider_id"),
                    "api_base": b.get("api_base"), "author": b.get("author"),
                    "kind": b.get("kind"), "model": b.get("model"),
                    "repo": b.get("repo") or REPO,
                    "result": public_result(b)})
    return {"prs": out}


@app.get("/api/prs/{pr}")
def api_get_pr(pr: int, request: Request):
    """门禁查询（X-Hub-Token）或登录用户查看。"""
    if request.headers.get("x-hub-token") and HUB_TOKEN and hmac.compare_digest(
            request.headers["x-hub-token"], HUB_TOKEN):
        pass
    elif not current_user(request):
        raise HTTPException(401, "login required")
    binding = get_binding(pr)
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


# ---- 身份绑定（评论绑定码，无需 OAuth App） --------------------------------

@app.post("/api/prs/{pr}/bind/start")
def api_bind_start(pr: int, request: Request):
    user = current_user(request)
    binding = get_binding(pr)
    if not binding:
        raise HTTPException(404, "该 PR 未注册验证")
    if user and (binding.get("author") or "").lower() == user.lower():
        return {"already_bound": True, "login": user}
    code = "MQ-" + pysecrets.token_hex(4).upper()
    BINDS[str(pr)] = {"code": code, "exp": int(time.time()) + BIND_TTL}
    return {"code": code, "expires_in": BIND_TTL,
            "instruction": f"请在 PR #{pr} 下评论: {code}（用提交 PR 的 GitHub 账号），然后回到这里点「我已评论」"}


@app.post("/api/prs/{pr}/bind/confirm")
def api_bind_confirm(pr: int, request: Request):
    binding = get_binding(pr)
    if not binding:
        raise HTTPException(404, "该 PR 未注册验证")
    rec = BINDS.get(str(pr))
    if not rec or rec["exp"] < time.time():
        raise HTTPException(400, "绑定码不存在或已过期，请重新获取")
    author = (binding.get("author") or "").lower()
    if DEV_MODE:
        login = author or "dev-user"
    else:
        comments = gh_api("GET",
                          f"/repos/{binding['repo']}/issues/{pr}/comments"
                          "?per_page=100&sort=created&direction=desc")
        if isinstance(comments, dict) and comments.get("__error__"):
            raise HTTPException(502, f"读取 PR 评论失败: {comments.get('message')}")
        login = ""
        for c in comments if isinstance(comments, list) else []:
            if rec["code"] in (c.get("body") or ""):
                login = ((c.get("user") or {}).get("login") or "").lower()
                break
        if not login:
            raise HTTPException(400, "未在 PR 评论中找到绑定码（用提交 PR 的账号评论后重试）")
        if login != author:
            raise HTTPException(403, f"评论者 @{login} 不是 PR 作者 @{binding.get('author')}，拒绝绑定")
    BINDS.pop(str(pr), None)
    resp = JSONResponse({"ok": True, "login": login})
    resp.set_cookie("mq_session", make_session(login), httponly=True, samesite="lax",
                    max_age=7 * 86400, secure=BASE_URL.startswith("https"))
    return resp


# ---- Key 与运行 ------------------------------------------------------------

@app.post("/api/prs/{pr}/key")
async def api_submit_key(pr: int, request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "请先绑定身份（评论绑定码）")
    binding = get_binding(pr)
    if not binding:
        raise HTTPException(404, "该 PR 未注册验证")
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
    if not key.startswith("sk-") or len(key) < 16:
        raise HTTPException(400, "Key 格式可疑（应以 sk- 开头且长度足够）")
    if base and not base.startswith("https://") and "127.0.0.1" not in base:
        raise HTTPException(400, "覆盖端点必须 https")
    KEYS[str(pr)] = {"key": key, "base": base or None, "exp": int(time.time()) + KEY_TTL}
    return {"ok": True, "expires_in": KEY_TTL,
            "hint": "Key 仅存内存，触发测试后即消费；过期自动焚毁"}


@app.post("/api/prs/{pr}/run")
def api_run(pr: int, request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "请先绑定身份（评论绑定码）")
    binding = get_binding(pr)
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

        result = {"status": "completed", "verdict": verdict, "engine": engine_v,
                  "tested_base": tested_base,
                  "finished_at": int(time.time()), "report_url": report_url}
        with _store_lock:
            store = load_store()
            store["prs"][str(pr)]["last_result"] = result
            store["prs"][str(pr)]["last_run_at"] = int(time.time())
            binding = store["prs"][str(pr)]
            save_store(store)
        pub = public_result(binding)

        comment = post_pr_comment(
            binding["repo"], pr,
            md + (f"\n\n---\n- 实测端点: `{tested_base}`"
                  + ("\n- ⚠️ 实测端点与 PR 声明的 api_base 不一致，请先更新 PR" if pub["base_mismatch"] else "")
                  + f"\n- 引擎: `{engine_v}` · 报告: {report_url}"
                  + ("\n- ✅ 验证通过：请在 PR 下评论 `/mq-done` 触发自动合并"
                     if pub["verified"] else "\n- ❌ 未通过：可修复后在 Hub 重新提交 Key 复测")))
        return {"ok": True, **pub, "github": {"comment": comment}}
    finally:
        lk.release()


@app.get("/reports/{pr}/{name}")
def get_report(pr: int, name: str):
    safe = Path(name).name
    p = REPORTS_DIR / str(pr) / safe
    if not p.is_file():
        raise HTTPException(404, "report not found")
    return FileResponse(p, media_type="text/markdown" if safe.endswith(".md") else "application/json")


# ---- OAuth（可选升级，配置了才显示） ---------------------------------------

@app.get("/auth/github/callback")
def oauth_callback(request: Request, code: str = "", state: str = ""):
    if not GITHUB_CLIENT_ID:
        return HTMLResponse("<h3>OAuth 未配置</h3>", 503)
    req = urllib.request.Request(
        "https://github.com/login/oauth/access_token",
        data=urllib.parse.urlencode({
            "client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET,
            "code": code, "redirect_uri": f"{BASE_URL}/auth/github/callback"}).encode(),
        headers={"accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            tok = json.loads(resp.read()).get("access_token", "")
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(f"<h3>OAuth 失败</h3><pre>{type(e).__name__}: {e}</pre>", 502)
    if not tok:
        return HTMLResponse("<h3>OAuth 失败</h3>", 401)
    req2 = urllib.request.Request("https://api.github.com/user",
                                  headers={"user-agent": "mq-hub/0.2",
                                           "authorization": f"Bearer {tok}"})
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
    return RedirectResponse(
        "https://github.com/login/oauth/authorize?client_id=" + GITHUB_CLIENT_ID +
        "&redirect_uri=" + urllib.parse.quote(f"{BASE_URL}/auth/github/callback") +
        "&scope=read%3Auser")


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
.code-box{font-size:1.25em;font-weight:700;color:var(--ok);background:#010409;border:1px dashed var(--ok);border-radius:8px;padding:10px 14px;margin:10px 0;user-select:all}
.prlink{display:inline-block;margin:8px 0 4px;font-weight:600}
</style></head><body><div class="wrap">
<h1>🔬 MQ Hub <span class="muted">— 中转站官方验证入口</span></h1>
<p class="muted">临时 Key 仅存内存：一次性消费 · TTL_EXPIRE 分钟过期 · 绝不落盘 · 报告自动回贴 PR · 评论 /mq-done 自动合并。<br>
收录 ≠ 推荐，验证通过 ≠ 安全。请提交<b>低额度、短有效期</b>的专用 Key，测试完成后立即吊销。</p>
<div id="status" class="card">加载中…</div>
<div id="main"></div>
<div class="card muted"><b>流程</b>：PR 提交 providers/*.json → Action 自动注册本站 → 提交者在本站获取绑定码并到 PR 评论（GitHub 即身份证明）→
提交临时 Key → 运行验证 → 报告回贴 PR → 在 PR 评论 <code>/mq-done</code> 自动合并。<br>
<b>注意</b>：实测端点必须与 PR 声明的 <code>api_base</code> 一致，不一致会被拦截。</div>
</div>
<script>
async function j(url, opts) { const r = await fetch(url, opts); const d = await r.json().catch(()=>({})); if (!r.ok) throw new Error(d.detail || r.status); return d; }
async function boot() {
  const st = document.getElementById('status');
  let me = null;
  try { me = await j('/api/me'); } catch (e) {}
  const who = me ? '已绑定身份：<code>' + me.login + '</code>' : '未绑定身份（在每个 PR 面板里用「绑定码」完成身份验证）';
  st.innerHTML = '<b>状态</b> · ' + who;
  const main = document.getElementById('main');
  const d = await j('/api/prs');
  if (!d.prs.length) { main.innerHTML = '<div class="card muted">暂无已注册的待验证 PR。提交 PR 修改 <code>providers/*.json</code> 后会自动出现在这里。</div>'; return; }
  main.innerHTML = '';
  window.PRMAP = {};
  for (const b of d.prs) {
    window.PRMAP[b.pr] = b;
    const res = b.result || {};
    const mine = me && me.login && b.author && me.login.toLowerCase() === b.author.toLowerCase();
    const div = document.createElement('div'); div.className = 'card';
    const badge = res.verified ? '<span class="tag ok">✅ 已通过</span>'
      : (res.status === 'completed' ? '<span class="tag err">❌ ' + (res.verdict||'') + (res.base_mismatch?' + 端点不一致':'') + '</span>' : '<span class="tag warn">⏳ 待验证</span>');
    let inner = `<b><a href="https://github.com/${b.repo||'cfrs2005/awesome-claude-code-relay'}/pull/${b.pr}" target="_blank" rel="noopener">#${b.pr} ${b.provider_id||''} ↗</a></b> ${badge}` +
      (mine ? ' <span class="tag">我是作者</span>' : '') +
      `<br><span class="muted">作者 <code>${b.author||'?'}</code> · 端点 <code>${b.api_base||'—（PR 未填 api_base）'}</code> · 测试模型 <code>${b.model||'claude-haiku-4-5'}</code>` +
      (res.report_url ? ` · <a href="${res.report_url}">报告</a>` : '') + `</span>`;
    if (res.verified) {
      if (mine) inner += `<hr style="border-color:var(--bd)"><span class="ok">✅ 验证通过 —— 去 PR 评论 <code>/mq-done</code> 即可自动合并</span>`;
    } else if (me && !mine) {
      inner += `<hr style="border-color:var(--bd)"><span class="muted">此 PR 归 @${b.author||'?'}，仅作者本人可完成验证（你当前绑定身份：${me.login}）</span>`;
    } else {
      inner += `<hr style="border-color:var(--bd)">
      <div id="bind-${b.pr}" style="${me ? 'display:none' : ''}"><button class="primary" onclick="bindStart(${b.pr})">① 获取绑定码（验证我是 PR 作者）</button>
      <span class="muted">仅 PR 作者能完成绑定：用提交 PR 的 GitHub 账号在 PR 下评论绑定码</span></div>
      <div id="key-${b.pr}" style="${me ? '' : 'display:none'}">
        <label>临时 API Key（一次性，触发即焚）</label>
        <input id="k-${b.pr}" placeholder="sk-..." autocomplete="off">
        <label class="muted">覆盖端点（可选；留空 = PR 声明的 api_base；不一致会被拦截）</label>
        <input id="u-${b.pr}" placeholder="https://api.example.com（可选）">
        <button onclick="submitKey(${b.pr})">② 提交 Key</button>
        <button class="primary" onclick="runTest(${b.pr})">③ 运行验证</button>
      </div>`;
    }
    inner += `<div id="m-${b.pr}" class="muted" style="margin-top:10px"></div>`;
    div.innerHTML = inner;
    main.appendChild(div);
  }
  window.bindStart = async (pr) => {
    const m = document.getElementById('m-'+pr); m.textContent = '生成绑定码…';
    try {
      const r = await j(`/api/prs/${pr}/bind/start`, {method:'POST'});
      if (r.already_bound) { document.getElementById('bind-'+pr).style.display='none'; document.getElementById('key-'+pr).style.display='block'; m.textContent='✅ 身份已绑定'; return; }
      const repo = (window.PRMAP[pr] || {}).repo || 'cfrs2005/awesome-claude-code-relay';
      document.getElementById('bind-'+pr).innerHTML =
        `<div class="code-box">${r.code}</div>
        <a class="prlink" href="https://github.com/${repo}/pull/${pr}" target="_blank" rel="noopener">➡️ 点这里打开 PR #${pr} 评论区，把上面的绑定码粘贴为评论（用提交 PR 的 GitHub 账号）</a><br>
        <button class="primary" onclick="bindConfirm(${pr})">我已评论，确认绑定</button>`;
    } catch (e) { m.innerHTML = '<span class="err">❌ ' + e.message + '</span>'; }
  };
  window.bindConfirm = async (pr) => {
    const m = document.getElementById('m-'+pr); m.textContent = '校验评论中…';
    try {
      await j(`/api/prs/${pr}/bind/confirm`, {method:'POST'});
      document.getElementById('bind-'+pr).style.display='none';
      document.getElementById('key-'+pr).style.display='block';
      m.innerHTML = '<span class="ok">✅ 身份已绑定（7 天有效），可直接提交 Key</span>';
      setTimeout(boot, 800);
    } catch (e) { m.innerHTML = '<span class="err">❌ ' + e.message + '</span>'; }
  };
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
      m.innerHTML = r.verified
        ? '<span class="ok">✅ 验证通过，报告已回贴 PR — 去 PR 评论 <b>/mq-done</b> 自动合并</span>'
        : `<span class="err">验证完成：${r.verdict||''}${r.base_mismatch?'（端点不一致）':''} — <a href="${r.report_url}">报告</a></span>`;
      setTimeout(boot, 2000);
    } catch (e) { m.innerHTML = '<span class="err">❌ ' + e.message + '</span>'; }
  };
}
boot();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE.replace("TTL_EXPIRE", str(KEY_TTL // 60))


@app.get("/api/me")
def api_me(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "not bound")
    return {"login": user}
