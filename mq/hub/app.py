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
import hashlib
import hmac
import json
import os
import re
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

# 契约层（结论文案 / 配色语义 / 放行集合）与引擎、脚本共用一份，避免 Hub 自成一套。
# 仓库形态：mq/hub/app.py → mq/contracts.py
# 部署形态：/opt/mq-hub/app.py → /opt/mq-hub/contracts.py
_MQ_DIR = Path(__file__).resolve().parent.parent
if not (_MQ_DIR / "contracts.py").is_file():
    _MQ_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_MQ_DIR))
from contracts import MERGEABLE, VERDICT_TONE  # noqa: E402

# ---------------------------------------------------------------- config ---

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8710").rstrip("/")
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
ENGINE_PATH = os.environ.get("ENGINE_PATH", str(Path(__file__).parent.parent / "mq.py"))
RENDER_SCRIPT = os.environ.get("RENDER_SCRIPT", str(Path(__file__).parent / "render_report.py"))
# 目录索引由 scripts/build_providers_index.py 在部署时生成，跟着发布包一起走。
PROVIDERS_INDEX = os.environ.get("PROVIDERS_INDEX",
                                 str(Path(__file__).parent / "providers-index.json"))
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
    verified = (r.get("status") == "completed" and r.get("verdict") in MERGEABLE
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
        "requested_model": r.get("requested_model"),
        "tested_model": r.get("tested_model"),
        "model_substituted": r.get("model_substituted", False),
    }


def verification_url(pr: int) -> str:
    """Return the stable, shareable verification workspace URL for a PR."""
    return f"{BASE_URL}/pr/{pr}"


# ---------------------------------------------------------------- engine ---

def previous_report(pr: int) -> Path | None:
    """找出该 PR 上一次成功产出的 report.json，用于检测模型目录 / 上游变化。"""
    d = REPORTS_DIR / str(pr)
    if not d.is_dir():
        return None
    candidates = sorted(d.glob("*/report.json"), reverse=True)
    return candidates[0] if candidates else None


def run_engine(base_url: str, key: str, model: str, out_dir: Path,
               prev: Path | None = None) -> tuple[dict, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / "report.json", out_dir / "report.md"
    fd, kp = tempfile.mkstemp(suffix=".key")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(key)
        os.chmod(kp, 0o600)
        cmd = [sys.executable, ENGINE_PATH, "--base-url", base_url, "--key-file", kp,
               "--model", model, "--json", str(jp), "--markdown", str(mp)]
        if prev and prev.exists():
            cmd += ["--previous-report", str(prev)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=RUN_TIMEOUT)  # noqa: S603
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


VERSION_FILE = Path(os.environ.get("VERSION_FILE",
                                   Path(__file__).parent / "VERSION"))


def hub_version() -> str:
    """部署时由 scripts/deploy.sh 写入。读不到就报 dev，别假装有版本号。"""
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


def engine_version() -> str:
    """从部署的引擎文件里读 MQ_VERSION，用来验证「部署的到底是哪版引擎」。"""
    try:
        text = Path(ENGINE_PATH).read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r'^MQ_VERSION\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else ""


@app.get("/healthz")
def healthz():
    # 部署流水线会校验这里的 version / engine_version，所以不要把缺项藏起来。
    return {"ok": True,
            "version": hub_version(),
            "engine": Path(ENGINE_PATH).exists(),
            "engine_version": engine_version(),
            "gh_token": bool(GITHUB_TOKEN),
            "oauth": bool(GITHUB_CLIENT_ID)}


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
    return {"ok": True, "pr": pr, "api_base": binding["api_base"],
            "verification_url": verification_url(pr)}


@app.get("/api/prs")
def api_list_prs():
    """公开列表（信息本就公开于仓库/PR）：不含任何 Key。"""
    with _store_lock:
        store = load_store()
    out = []
    for b in sorted(store["prs"].values(), key=lambda x: -x["pr"]):
        state = pr_info(b.get("repo") or REPO, b["pr"]).get("state", "unknown")
        out.append({"pr": b["pr"], "provider_id": b.get("provider_id"),
                    "api_base": b.get("api_base"), "author": b.get("author"),
                    "kind": b.get("kind"), "model": b.get("model"),
                    "repo": b.get("repo") or REPO,
                    "pr_state": state,
                    "verification_url": verification_url(b["pr"]),
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
        return {"registered": False, "requires_verification": False, "verified": False,
                "verification_url": verification_url(pr)}
    return {
        "registered": True,
        "repo": binding["repo"],
        "provider_id": binding["provider_id"],
        "api_base": binding["api_base"],
        "author": binding["author"],
        "kind": binding["kind"],
        "requires_verification": binding["requires_verification"],
        "pr_state": pr_info(binding["repo"], pr).get("state", "unknown"),
        "verification_url": verification_url(pr),
        "key_ready": str(pr) in KEYS and KEYS[str(pr)]["exp"] > time.time(),
        "result": public_result(binding),
    }


# ---- 身份绑定（评论绑定码，无需 OAuth App） --------------------------------

@app.post("/api/prs/{pr}/bind/start")
def api_bind_start(pr: int, request: Request):
    raise HTTPException(
        410,
        "服务端接收 Key 的流程已下线。MQ 引擎现在在提交者本机运行，"
        "报告贴进 PR 即可。见 https://github.com/cfrs2005/awesome-claude-code-relay")
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
    raise HTTPException(
        410,
        "服务端接收 Key 的流程已下线。MQ 引擎现在在提交者本机运行，"
        "报告贴进 PR 即可。见 https://github.com/cfrs2005/awesome-claude-code-relay")
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
    raise HTTPException(
        410,
        "服务端接收 Key 的流程已下线。MQ 引擎现在在提交者本机运行，"
        "报告贴进 PR 即可。见 https://github.com/cfrs2005/awesome-claude-code-relay")
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
    raise HTTPException(
        410,
        "服务端接收 Key 的流程已下线。MQ 引擎现在在提交者本机运行，"
        "报告贴进 PR 即可。见 https://github.com/cfrs2005/awesome-claude-code-relay")
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
        prev = previous_report(pr)
        doc, md = run_engine(tested_base, keyrec["key"],
                             binding.get("model") or "claude-haiku-4-5-20251001",
                             out_dir, prev=prev)
        verdict = doc.get("verdict", {}).get("label", "inconclusive")
        engine_v = doc.get("engine", "?")
        # 人读的是 HTML 页；.md / .json 作为原始件保留
        report_url = f"{BASE_URL}/r/{pr}/{ts}"

        result = {"status": "completed", "verdict": verdict, "engine": engine_v,
                  "tested_base": tested_base,
                  "requested_model": (doc.get("meta") or {}).get("requested_model"),
                  "tested_model": (doc.get("meta") or {}).get("model"),
                  "model_substituted": bool(doc.get("substituted")),
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
                  + f"\n- 原始文件: {BASE_URL}/reports/{pr}/{ts}.md"
                  + f"\n- PR 验证工作台: {verification_url(pr)}"
                  + ("\n- ✅ 验证通过：请在 PR 下评论 `/mq-done` 触发自动合并"
                     if pub["verified"] else "\n- ❌ 未通过：可修复后在 Hub 重新提交 Key 复测")))
        return {"ok": True, **pub, "github": {"comment": comment}}
    finally:
        lk.release()


def _load_renderer():
    """加载 scripts/render_report.py（部署形态与仓库形态都能找到）。"""
    import importlib.util
    script = Path(RENDER_SCRIPT)
    if not script.is_file():
        alt = Path(__file__).resolve().parent.parent.parent / "scripts" / "render_report.py"
        script = alt if alt.is_file() else script
    if not script.is_file():
        raise HTTPException(500, f"render_report.py 缺失（找过 {RENDER_SCRIPT}）")
    spec = importlib.util.spec_from_file_location("render_report", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_PROVIDERS_CACHE = {"key": None, "value": []}


def load_providers():
    """读目录索引。文件缺失时返回空列表（首页会显示「尚未生成」而不是崩掉）。"""
    p = Path(PROVIDERS_INDEX)
    try:
        st = p.stat()
    except OSError:
        return []
    key = (str(p), st.st_mtime, st.st_size)
    if _PROVIDERS_CACHE["key"] == key:
        return _PROVIDERS_CACHE["value"]
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        items = doc.get("items") or []
    except (OSError, ValueError):
        items = []
    _PROVIDERS_CACHE.update({"key": key, "value": items})
    return items


def error_html(title, detail, hint="", status=404):
    """统一错误页。以前 404 直接返回 FastAPI 的 {"detail": "..."}，人类看到的是裸 JSON。"""
    try:
        body = _load_renderer().error_page(title, detail, hint)
    except Exception:  # noqa: BLE001  渲染器挂了也不能再挂一次
        body = f"<h3>{title}</h3><p>{detail}</p><p><a href='/'>返回首页</a></p>"
    return HTMLResponse(body, status_code=status)


def scan_reports():
    """扫描 REPORTS_DIR/{pr}/{ts}/report.json，返回报告索引条目（新→旧）。"""
    entries = []
    if not REPORTS_DIR.is_dir():
        return entries
    files = sorted(REPORTS_DIR.glob("*/[0-9]*/report.json"),
                   key=lambda f: f.parent.name, reverse=True)
    for jp in files[:200]:
        try:
            doc = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        meta = doc.get("meta") or {}
        checks = doc.get("checks") or []
        verdict = (doc.get("verdict") or {}).get("label") or "inconclusive"
        pr = jp.parent.parent.name
        ts = jp.parent.name
        # 旧报告（引擎 0.1.0）没有 expect_family，用目录里占比最大的家族代替，
        # 否则 86GameStore 这种纯 gpt 目录会被标成 Claude。
        fams = (doc.get("catalog") or {}).get("families") or {}
        family = meta.get("expect_family") or (
            max(fams, key=fams.get) if fams else "")
        ts_h = ts.replace("T", " ").replace("Z", "")
        entries.append({
            "pr": pr, "ts": ts,
            "when": f"{ts_h[:4]}-{ts_h[4:6]}-{ts_h[6:8]} {ts_h[9:11]}:{ts_h[11:13]}",
            "host": meta.get("host") or "—",
            "family": family,
            "mode": meta.get("mode") or "",
            "engine": doc.get("engine") or "?",
            "verdict": verdict,
            "tone": VERDICT_TONE.get(verdict, "info"),
            "n_pass": sum(1 for c in checks if c.get("status") == "PASS"),
            "total": len(checks),
            "url": f"/r/{pr}/{ts}",
        })
    return entries


def _render_report_html(report_json: Path) -> str:
    """用 scripts/render_report.py 把 report.json 渲成 HTML 页。"""
    mod = _load_renderer()
    return mod.build(json.loads(report_json.read_text(encoding="utf-8")))


@app.get("/r/{pr}/{ts}", response_class=HTMLResponse)
def view_report(pr: int, ts: str):
    """人类可读的报告页。原始 markdown / json 仍可通过 /reports/... 取。"""
    safe = Path(ts).name
    jp = REPORTS_DIR / str(pr) / safe / "report.json"
    if not jp.is_file():
        return error_html("找不到这份报告",
                          f"PR #{pr} 下没有 {safe} 这个时间点的报告存档。",
                          "报告可能已被清理，或者链接里的时间戳不完整。")
    return HTMLResponse(_render_report_html(jp))


@app.get("/reports/{pr}/{name}")
def get_report(pr: int, name: str):
    safe = Path(name).name
    p = REPORTS_DIR / str(pr) / safe
    if not p.is_file() and safe.endswith(".md"):
        p = REPORTS_DIR / str(pr) / safe[:-3] / "report.md"
    if not p.is_file() and safe.endswith(".json"):
        p = REPORTS_DIR / str(pr) / safe[:-5] / "report.json"
    if not p.is_file():
        raise HTTPException(404, "report not found")
    return FileResponse(p, media_type="text/markdown" if p.name.endswith(".md") else "application/json")


@app.get("/pr/{pr}", response_class=HTMLResponse)
def pr_workspace(pr: int):
    """单个 PR 的报告列表。没有报告时给出该 PR 的复现指引。"""
    allx = [e for e in scan_reports() if e["pr"] == str(pr)]
    return HTMLResponse(_load_renderer().build_index(allx, mode="single"))


# ---- OAuth（可选升级，配置了才显示） ---------------------------------------

@app.get("/auth/github/callback")
def oauth_callback(request: Request, code: str = "", state: str = ""):
    if not GITHUB_CLIENT_ID:
        return error_html("OAuth 未配置",
                          "本站没有启用 GitHub 登录，这不影响查看报告。",
                          "绑定与登录是可选能力。", status=503)
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
        # 异常文本来自上游响应，必须转义后再进 HTML（原来直接拼进 <pre>）
        return error_html("GitHub 登录失败",
                          "无法与 GitHub 完成授权换取，请稍后重试。",
                          f"{type(e).__name__}: {e}", status=502)
    if not tok:
        return error_html("GitHub 登录失败",
                          "GitHub 没有返回访问令牌，可能是授权被取消。",
                          "可以返回首页继续浏览报告。", status=401)
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
        return error_html("OAuth 未配置",
                          "本站没有启用 GitHub 登录，这不影响查看报告。",
                          "绑定与登录是可选能力。", status=503)
    return RedirectResponse(
        "https://github.com/login/oauth/authorize?client_id=" + GITHUB_CLIENT_ID +
        "&redirect_uri=" + urllib.parse.quote(f"{BASE_URL}/auth/github/callback") +
        "&scope=read%3Auser")


# ---------------------------------------------------------------- page -----

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(_load_renderer().build_index(
        scan_reports(), providers=load_providers()))


@app.get("/api/me")
def api_me(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "not bound")
    return {"login": user}
