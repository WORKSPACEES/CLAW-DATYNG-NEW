# server_api.py — главный API сервер CLAW-DATYNG
# Отвечает за: авторизацию, аккаунты, настройки, фронтенд
# Проксирует задачи на воркер-серверы платформ
# Запуск: uvicorn server_api:app --host 0.0.0.0 --port 8001

import asyncio
import json
import re
import secrets
import time
import uuid
import http.client
import socks
import ssl
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib import request, error
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


class SocksHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, proxy_host, proxy_port, proxy_user, proxy_pass, timeout=30):
        super().__init__(host, port, timeout=timeout)
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        self._proxy_user = proxy_user
        self._proxy_pass = proxy_pass

    def connect(self):
        sock = socks.socksocket()
        sock.set_proxy(
            socks.SOCKS5, self._proxy_host, self._proxy_port,
            username=self._proxy_user, password=self._proxy_pass, rdns=True
        )
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.port))
        context = ssl.create_default_context()
        self.sock = context.wrap_socket(sock, server_hostname=self.host)

from shared import (
    supabase, leads_supabase, require_auth, get_session, create_session,
    hash_password, verify_password, get_ai_settings, save_ai_settings,
    get_team_owner_emails, get_groq_keys, get_gemini_keys,
    append_task_log, build_system_prompt, CANCEL_FLAGS, ACCESS_CODE,
    push_split_log_sync,
)

# ── URL воркер-серверов ───────────────────────────────────
# Замени на реальные URL после деплоя на Render
MAMBA_SERVER_URL      = "https://claw-datyng-new-j1ea.onrender.com"
LOVELAZ_SERVER_URL    = "https://lovelaz-server.onrender.com"
TWINBY_SERVER_URL     = "https://claw-datyng-new-1-1f2q.onrender.com"
VZNAKOMSTVE_SERVER_URL = "https://vznakomstve-server.onrender.com"

PLATFORM_URLS = {
    "mamba":        MAMBA_SERVER_URL,
    "lovelaz":      LOVELAZ_SERVER_URL,
    "twinby":       TWINBY_SERVER_URL,
    "vznakomstve":  VZNAKOMSTVE_SERVER_URL,
}

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="CLAW-AI API Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Helper: проксирование на воркер ──────────────────────

async def proxy_to_worker(platform: str, path: str, payload: dict, authorization: str = None) -> dict:
    base_url = PLATFORM_URLS.get(platform.lower())
    if not base_url:
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform}")

    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{base_url}{path}", json=payload, headers=headers)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Воркер {platform} недоступен")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Воркер {platform} не ответил вовремя")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not resp.content:
        raise HTTPException(
            status_code=502,
            detail=f"Воркер {platform} вернул пустой ответ (возможно, ещё не проснулся после сна)"
        )

    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail=f"Воркер {platform} вернул не-JSON ответ (status={resp.status_code}): {resp.text[:200]}"
        )

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=data.get("detail") or data)

    return data

# ── Pydantic Models ───────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    access_code: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class UpdateProfileRequest(BaseModel):
    username: str = ""

class AiSettingsPayload(BaseModel):
    groq_api_key: str = ""
    groq_api_keys: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    bot_name: str = ""
    bot_age: str = ""
    bot_gender: str = "female"
    location: str = ""
    persona: str = ""
    goal: str = ""
    stop_topics: str = ""
    contacts: str = ""
    contacts_trigger: str = ""
    tg_chat_id: str = ""
    gemini_api_keys: str = ""
    proxy_protocol: str = ""
    proxy_host: str = ""
    proxy_port: str = ""
    proxy_login: str = ""
    proxy_password: str = ""
    user_agent: str = ""

class LikesTaskRequest(BaseModel):
    account_id: str
    limit: int = 10
    platform: str = "mamba"

class AutoReplyTaskRequest(BaseModel):
    account_id: str
    max_dialogs: int = 20
    platform: str = "mamba"

class StopTaskRequest(BaseModel):
    account_id: str

class TeamInviteRequest(BaseModel):
    email: str
    role: str = "manager"

class AcceptInviteRequest(BaseModel):
    invite_id: str
    email: str = ""

class RejectInviteRequest(BaseModel):
    invite_id: str
    email: str = ""

class CreateTabRequest(BaseModel):
    name: str
    platform: str = "Mamba"

class AssignTabRequest(BaseModel):
    account_id: str
    tab_id: str

class AccountRunStatusPayload(BaseModel):
    run_status: str = "idle"
    run_task: str = ""
    run_note: str = ""
    is_blocked: bool | None = None

class AccountUpdateRequest(BaseModel):
    name: str | None = None

class SplitLogPushRequest(BaseModel):
    account_id: str
    messages: list[str]

class ReportTgAccountRequest(BaseModel):
    tg_username: str
    label: str = ""

class ReportEntryRequest(BaseModel):
    tg_account: str
    date: str
    visits: int = 0
    bookings: int = 0
    cancels: int = 0
    notes: str = ""

class ProxySettingsModel(BaseModel):
    id: str
    host: str
    port: int
    username: str
    password: str
    use_proxy: bool = True
    user_agent: str = ""

class ConnectAccountRequest(BaseModel):
    account_name: str
    profile_url: str
    cookies_raw: str = ""
    platform: str = "Mamba"
    twinby_email: str = ""
    twinby_code: str = ""
    vzn_email: str = ""
    vzn_code: str = ""
    intcity_email: str = ""
    intcity_password: str = ""

class SetChainRequest(BaseModel):
    account_id: str
    chain: list[str]

# ── Auth ──────────────────────────────────────────────────

@app.post("/api/auth/register")
def register(payload: RegisterRequest):
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Некорректный email")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Пароль должен быть не менее 6 символов")
    if payload.access_code.strip() != ACCESS_CODE:
        raise HTTPException(status_code=403, detail="Неверный код доступа")
    existing = supabase.table("app_users").select("id").eq("email", email).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Пользователь уже зарегистрирован")
    password_hash = hash_password(payload.password)
    res = supabase.table("app_users").insert({"email": email, "password_hash": password_hash}).execute()
    user = res.data[0]
    token = create_session(user["id"], user["email"])
    return {"ok": True, "token": token, "email": user["email"]}

@app.post("/api/auth/login")
def login(payload: LoginRequest):
    email = payload.email.strip().lower()
    res = supabase.table("app_users").select("*").eq("email", email).execute()
    if not res.data:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    user = res.data[0]
    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    token = create_session(user["id"], user["email"])
    return {"ok": True, "token": token, "email": user["email"]}

@app.get("/api/auth/me")
def auth_me(authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    res = supabase.table("app_users").select("username").eq("id", session["user_id"]).execute()
    username = res.data[0].get("username") if res.data else ""
    return {"ok": True, "email": session["email"], "username": username}

@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):].strip()
        supabase.table("app_sessions").delete().eq("token", token).execute()
    return {"ok": True}

@app.post("/api/auth/update-profile")
def api_update_profile(payload: UpdateProfileRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    if payload.username:
        supabase.table("app_users").update({"username": payload.username}).eq("id", session["user_id"]).execute()
    return {"ok": True}

@app.post("/api/auth/change-password")
def change_password(payload: ChangePasswordRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    res = supabase.table("app_users").select("*").eq("id", session["user_id"]).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user = res.data[0]
    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Текущий пароль неверен")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Новый пароль должен быть не менее 6 символов")
    supabase.table("app_users").update({"password_hash": hash_password(payload.new_password)}).eq("id", user["id"]).execute()
    return {"ok": True}

# ── Accounts ──────────────────────────────────────────────

@app.get("/api/accounts")
def get_accounts(authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    res = supabase.table("accounts").select("*").in_("owner_email", owner_emails).order("created_at", desc=True).execute()
    return {"ok": True, "accounts": res.data or []}

@app.patch("/api/accounts/{account_id}")
def api_update_account(account_id: str, payload: AccountUpdateRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    account_res = supabase.table("accounts").select("id").eq("id", account_id).in_("owner_email", owner_emails).execute()
    if not account_res.data:
        raise HTTPException(status_code=403, detail="Нет доступа")
    update_data = {}
    if payload.name is not None:
        update_data["name"] = payload.name
    if update_data:
        supabase.table("accounts").update(update_data).eq("id", account_id).execute()
    return {"ok": True}

@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: str, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    account_res = supabase.table("accounts").select("id").eq("id", account_id).in_("owner_email", owner_emails).execute()
    if not account_res.data:
        raise HTTPException(status_code=403, detail="Нет доступа")
    supabase.table("accounts").delete().eq("id", account_id).execute()
    return {"ok": True}

@app.get("/api/accounts/reserved-ids")
def api_get_reserved_ids(authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    res = supabase.table("accounts").select("id, reserve_chain").in_("owner_email", owner_emails).execute()
    reserved = set()
    for row in res.data or []:
        for rid in (row.get("reserve_chain") or []):
            reserved.add(rid)
    return {"ok": True, "reserved_ids": list(reserved)}

@app.post("/api/accounts/check-statuses")
async def api_check_account_statuses(authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    accounts_res = supabase.table("accounts").select("id, is_blocked, platform").in_("owner_email", owner_emails).execute()

    async def check_one(row):
        account_id = row["id"]
        platform = (row.get("platform") or "mamba").lower()
        if row.get("is_blocked"):
            return {"account_id": account_id, "status": "blocked", "skipped": True}
        try:
            base_url = PLATFORM_URLS.get(platform, MAMBA_SERVER_URL)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{base_url}/api/check-status/{account_id}")
                return resp.json()
        except Exception as e:
            return {"account_id": account_id, "status": "unknown", "reason": str(e)}

    results = await asyncio.gather(*(check_one(row) for row in (accounts_res.data or [])))
    return {"ok": True, "results": results}

@app.post("/api/accounts/{account_id}/run-status")
def api_set_account_run_status(account_id: str, payload: AccountRunStatusPayload, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    account_res = supabase.table("accounts").select("id").eq("id", account_id).in_("owner_email", owner_emails).execute()
    if not account_res.data:
        raise HTTPException(status_code=403, detail="Нет доступа")
    status = payload.run_status or "idle"
    update_data = {"run_status": status, "run_task": payload.run_task or "", "run_note": payload.run_note or ""}
    if payload.is_blocked is True:
        update_data["is_blocked"] = True
    if status == "running":
        update_data["run_started_by"] = session["email"]
        update_data["run_started_at"] = datetime.now().isoformat()
    else:
        update_data["run_started_by"] = ""
        update_data["run_started_at"] = None
        update_data["run_note"] = ""
    supabase.table("accounts").update(update_data).eq("id", account_id).execute()
    return {"ok": True, "account_id": account_id, **update_data}

@app.post("/api/accounts/{account_id}/chain")
def api_set_chain(account_id: str, payload: SetChainRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    main_res = supabase.table("accounts").select("id").eq("id", account_id).in_("owner_email", owner_emails).limit(1).execute()
    if not main_res.data:
        raise HTTPException(status_code=404, detail="Анкета не найдена")
    clean_chain = [str(rid).strip() for rid in payload.chain if str(rid).strip() and str(rid).strip() != account_id]
    clean_chain = list(dict.fromkeys(clean_chain))
    supabase.table("accounts").update({"reserve_chain": clean_chain}).eq("id", account_id).execute()
    return {"ok": True, "chain": clean_chain}

@app.get("/api/accounts/{account_id}/chain")
def api_get_chain(account_id: str):
    res = supabase.table("accounts").select("reserve_chain").eq("id", account_id).execute()
    if not res.data:
        return {"ok": True, "chain": []}
    return {"ok": True, "chain": res.data[0].get("reserve_chain") or []}

# ── Connect Account ───────────────────────────────────────

@app.post("/api/connect")
async def connect_account(payload: ConnectAccountRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    platform_lower = payload.platform.strip().lower()

    if not payload.profile_url.startswith("http") and platform_lower != "vznakomstve":
        raise HTTPException(status_code=400, detail="profile_url должен начинаться с http")

    cookies = []
    x_token = ""

    # ── Twinby ──
    if platform_lower == "twinby":
        if not payload.twinby_email or not payload.twinby_code:
            raise HTTPException(status_code=400, detail="Введи email и код из письма")
        import json as _json, asyncio
        from proxy_loader import get_proxy
        _proxy = get_proxy("twinby")

        def _do_confirm():
            if not (_proxy and _proxy.get("host") and _proxy.get("username")):
                raise RuntimeError("Прокси не настроен для Twinby — подключение без прокси запрещено")
            conn = SocksHTTPSConnection(
                "twinby.ru", 443,
                _proxy["host"], int(_proxy.get("port") or 1080),
                _proxy.get("username"), _proxy.get("password"),
                timeout=30,
            )
            body = _json.dumps({"login": payload.twinby_email, "provider": "email", "code": payload.twinby_code}).encode()
            conn.request("POST", "/api/auth/v2/auth/confirm", body=body, headers={
                "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Dart/3.11 (dart:io)",
            })
            resp = conn.getresponse()
            status = resp.status
            raw = resp.read()
            conn.close()
            return status, raw

        try:
            status, raw = await asyncio.to_thread(_do_confirm)
        except Exception as e:
            print(f"[TWINBY CONNECT ERROR] {type(e).__name__}: {e!r}", flush=True)
            raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

        if status != 200:
            raise HTTPException(status_code=400, detail=f"Неверный код или email (статус {status})")

        data = _json.loads(raw.decode("utf-8", errors="ignore"))
        token = data.get("accessToken") or data.get("token") or data.get("access") or data.get("jwt") or ""
        if not token:
            raise HTTPException(status_code=400, detail=f"Twinby не вернул токен. Ответ: {str(data)[:200]}")

        # Получаем фото профиля
        photo_url = ""
        try:
            from twinby_client import get_me
            me = get_me(token)
            avatar = me.get("avatar") or {}
            photo_url = avatar.get("file") or avatar.get("preview") or ""
            if not photo_url:
                photos = me.get("photos") or []
                if photos and isinstance(photos[0], dict):
                    photo_url = photos[0].get("file") or photos[0].get("preview") or ""
            print(f"[TWINBY CONNECT] фото: {photo_url}", flush=True)
        except Exception as e:
            print(f"[TWINBY CONNECT] фото не получено: {e}", flush=True)

        import uuid as _uuid
        account_id = str(_uuid.uuid4())

        public_account = {
            "id": account_id, "owner_email": session["email"], "platform": "Twinby",
            "name": payload.account_name or payload.twinby_email,
            "profile_url": "https://twinby.ru", "final_url": "https://twinby.ru",
            "title": payload.account_name or payload.twinby_email,
            "photo_url": photo_url, "cookies_count": 1, "cookies_valid": True,
            "session_valid": True, "session_reason": "JWT авторизация",
            "images_found": 0, "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        supabase.table("accounts").insert(public_account).execute()
        supabase.table("accounts_private").insert({"id": account_id, "cookies_raw": token}).execute()
        return {"ok": True, "account": public_account, "warning": None if photo_url else "Фото не найдено — добавь вручную."}

    # ── Vznakomstve ──
    if platform_lower == "vznakomstve" and payload.vzn_email and payload.vzn_code:
        import http.client as _hc, gzip as _gzip
        boundary = "getx-http-boundary-CLAWAI"

        conn = _hc.HTTPSConnection("meet.wcase.net", timeout=15)
        body_bytes = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"email\"\r\n\r\n{payload.vzn_email}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"code\"\r\n\r\n{payload.vzn_code}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"lang\"\r\n\r\nru\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"no_restore\"\r\n\r\n1\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        conn.request("POST", "/email", body=body_bytes, headers={
            "Accept": "application/json", "Accept-Encoding": "gzip",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body_bytes)),
            "User-Agent": "InDating v3.2.6 (302060), Android 9, G011A", "Host": "meet.wcase.net",
        })
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        if resp.getheader("Content-Encoding") == "gzip":
            raw = _gzip.decompress(raw)
        data1 = json.loads(raw.decode("utf-8", errors="ignore"))
        sid = data1.get("data", {}).get("sid") or data1.get("sessionId") or data1.get("sid") or data1.get("token") or ""
        print(f"[VZN LOGIN] step1 status={resp.status} sid={sid}", flush=True)
        if not sid:
            raise HTTPException(status_code=400, detail=f"Неверный код. Ответ: {str(data1)[:200]}")

        conn2 = _hc.HTTPSConnection("meet.wcase.net", timeout=15)
        body2 = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"token\"\r\n\r\n{sid}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"no_restore\"\r\n\r\n1\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        conn2.request("POST", "/login", body=body2, headers={
            "Accept": "application/json", "Accept-Encoding": "gzip",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body2)),
            "User-Agent": "InDating v3.2.6 (302060), Android 9, G011A", "Host": "meet.wcase.net",
        })
        resp2 = conn2.getresponse()
        raw2 = resp2.read()
        set_cookie = resp2.getheader("Set-Cookie") or ""
        conn2.close()
        if resp2.getheader("Content-Encoding") == "gzip":
            raw2 = _gzip.decompress(raw2)
        data2 = json.loads(raw2.decode("utf-8", errors="ignore"))

        phpsessid = ""
        for part in set_cookie.split(";"):
            if part.strip().startswith("PHPSESSID="):
                phpsessid = part.strip().split("=", 1)[1]
                break
        if not phpsessid:
            phpsessid = data2.get("sessionId") or data2.get("data", {}).get("sid") or ""
        if not phpsessid:
            raise HTTPException(status_code=400, detail=f"Не удалось получить сессию: {str(data2)[:200]}")

        x_token = data1.get("token") or data2.get("token") or sid or ""
        cookies_raw_vzn = json.dumps([
            {"name": "PHPSESSID", "value": phpsessid},
            {"name": "x_token", "value": x_token},
        ])
        payload.cookies_raw = cookies_raw_vzn

        from vznakomstve_client import parse_cookies as _vzn_parse, get_profile_photo as _vzn_get_photo
        import time as _time
        http_cookies = _vzn_parse(cookies_raw_vzn)
        photo_url = ""
        for _attempt in range(3):
            photo_url = _vzn_get_photo(http_cookies) or ""
            if photo_url:
                break
            _time.sleep(2)

        account_id = str(uuid.uuid4())
        public_account = {
            "id": account_id, "owner_email": session["email"], "platform": payload.platform,
            "name": payload.account_name or "Взнакомстве",
            "profile_url": "https://vznakomstve.com/app/",
            "final_url": "https://vznakomstve.com/app/",
            "title": payload.account_name or "Взнакомстве",
            "photo_url": photo_url, "cookies_count": 2, "cookies_valid": True,
            "session_valid": True, "session_reason": "Email авторизация",
            "images_found": 0, "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        supabase.table("accounts").insert(public_account).execute()
        supabase.table("accounts_private").insert({"id": account_id, "cookies_raw": cookies_raw_vzn}).execute()
        return {"ok": True, "account": public_account, "warning": None if photo_url else "Фото не найдено — добавь вручную."}

    # ── Mamba / Lovelaz — напрямую ──
    if platform_lower == "mamba":
        from mamba_client import parse_cookies as _m_parse, get_profile_photo as _m_photo
        cookies = _m_parse(payload.cookies_raw)
        photo_url = ""
        try:
            photo_url = _m_photo(cookies) or ""
        except Exception as e:
            print(f"[MAMBA CONNECT] фото не получено: {e}", flush=True)
        account_id = str(uuid.uuid4())
        public_account = {
            "id": account_id, "owner_email": session["email"], "platform": "Mamba",
            "name": payload.account_name or "Анкета",
            "profile_url": payload.profile_url, "final_url": payload.profile_url,
            "title": payload.account_name or "Анкета",
            "photo_url": photo_url, "cookies_count": len(cookies), "cookies_valid": True,
            "session_valid": True, "session_reason": "HTTP проверка",
            "images_found": 0, "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        supabase.table("accounts").insert(public_account).execute()
        supabase.table("accounts_private").insert({"id": account_id, "cookies_raw": payload.cookies_raw}).execute()
        return {"ok": True, "account": public_account, "warning": None if photo_url else "Фото не найдено — добавь вручную."}

    if platform_lower == "lovelaz":
        from lovelaz_client import parse_cookies as _lz_parse, get_profile_photo as _lz_photo
        cookies = _lz_parse(payload.cookies_raw)
        photo_url = ""
        try:
            photo_url = _lz_photo(cookies) or ""
        except Exception as e:
            print(f"[LOVELAZ CONNECT] фото не получено: {e}", flush=True)
        account_id = str(uuid.uuid4())
        public_account = {
            "id": account_id, "owner_email": session["email"], "platform": "Lovelaz",
            "name": payload.account_name or "Анкета",
            "profile_url": payload.profile_url, "final_url": payload.profile_url,
            "title": payload.account_name or "Анкета",
            "photo_url": photo_url, "cookies_count": len(cookies), "cookies_valid": True,
            "session_valid": True, "session_reason": "HTTP проверка",
            "images_found": 0, "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        supabase.table("accounts").insert(public_account).execute()
        supabase.table("accounts_private").insert({"id": account_id, "cookies_raw": payload.cookies_raw}).execute()
        return {"ok": True, "account": public_account, "warning": None if photo_url else "Фото не найдено — добавь вручную."}

    if platform_lower == "intcity":
        if not payload.cookies_raw or not payload.cookies_raw.strip().startswith("["):
            raise HTTPException(status_code=400, detail="Вставь Cookie Editor JSON")
        account_id = str(uuid.uuid4())
        public_account = {
            "id": account_id,
            "owner_email": session["email"],
            "platform": "intCity",
            "name": payload.account_name or payload.intcity_email,
            "profile_url": f"mailto:{payload.intcity_email}",
            "final_url": f"mailto:{payload.intcity_email}",
            "photo_url": "/intcity_logo.png",
            "session_valid": True,
            "session_reason": "OK",
            "images_found": 0,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        # Парсим Cookie Editor JSON и тянем токен со страницы
        mail_cookie_str = ""
        mail_token = ""
        try:
            import httpx as _httpx, re as _re
            cookie_list = json.loads(payload.cookies_raw)
            mail_cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookie_list if c.get("name") and c.get("value"))
            print(f"[intCity] Собрано кук: {len(cookie_list)}", flush=True)
            page_resp = _httpx.get(
                "https://e.mail.ru/inbox/",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    "Cookie": mail_cookie_str,
                },
                timeout=15,
                follow_redirects=True,
            )
            token_match = _re.search(r'[a-f0-9]{32}:[A-Za-z0-9_\-+/=.]{20,}', page_resp.text)
            if token_match:
                mail_token = token_match.group(0)
                print(f"[intCity] Токен получен: {mail_token[:20]}...", flush=True)
            else:
                print(f"[intCity] Токен не найден в HTML", flush=True)
        except Exception as e:
            print(f"[intCity] Ошибка при парсинге кук: {e}", flush=True)

        cookies_raw = json.dumps({
            "email": "",
            "password": "",
            "mail_cookie": mail_cookie_str,
            "mail_token": mail_token,
        })
        supabase.table("accounts").insert(public_account).execute()
        supabase.table("accounts_private").insert({"id": account_id, "cookies_raw": cookies_raw}).execute()
        warning = None if mail_token else "Токен не получен автоматически — вставь вручную на карточке"
        return {"ok": True, "account": public_account, "warning": warning}

    raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform_lower}")

    # ── Mamba / Lovelaz — напрямую ──
    if platform_lower == "mamba":
        from mamba_client import parse_cookies as _m_parse, get_profile_photo as _m_photo
        cookies = _m_parse(payload.cookies_raw)
        photo_url = ""
        try:
            photo_url = _m_photo(cookies) or ""
        except Exception as e:
            print(f"[MAMBA CONNECT] фото не получено: {e}", flush=True)
        account_id = str(uuid.uuid4())
        public_account = {
            "id": account_id, "owner_email": session["email"], "platform": "Mamba",
            "name": payload.account_name or "Анкета",
            "profile_url": payload.profile_url, "final_url": payload.profile_url,
            "title": payload.account_name or "Анкета",
            "photo_url": photo_url, "cookies_count": len(cookies), "cookies_valid": True,
            "session_valid": True, "session_reason": "HTTP проверка",
            "images_found": 0, "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        supabase.table("accounts").insert(public_account).execute()
        supabase.table("accounts_private").insert({"id": account_id, "cookies_raw": payload.cookies_raw}).execute()
        return {"ok": True, "account": public_account, "warning": None if photo_url else "Фото не найдено — добавь вручную."}

    if platform_lower == "lovelaz":
        from lovelaz_client import parse_cookies as _lz_parse, get_profile_photo as _lz_photo
        cookies = _lz_parse(payload.cookies_raw)
        photo_url = ""
        try:
            photo_url = _lz_photo(cookies) or ""
        except Exception as e:
            print(f"[LOVELAZ CONNECT] фото не получено: {e}", flush=True)
        account_id = str(uuid.uuid4())
        public_account = {
            "id": account_id, "owner_email": session["email"], "platform": "Lovelaz",
            "name": payload.account_name or "Анкета",
            "profile_url": payload.profile_url, "final_url": payload.profile_url,
            "title": payload.account_name or "Анкета",
            "photo_url": photo_url, "cookies_count": len(cookies), "cookies_valid": True,
            "session_valid": True, "session_reason": "HTTP проверка",
            "images_found": 0, "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        supabase.table("accounts").insert(public_account).execute()
        supabase.table("accounts_private").insert({"id": account_id, "cookies_raw": payload.cookies_raw}).execute()
        return {"ok": True, "account": public_account, "warning": None if photo_url else "Фото не найдено — добавь вручную."}

    if platform_lower == "intcity":
        if not payload.cookies_raw or not payload.cookies_raw.strip().startswith("["):
            raise HTTPException(status_code=400, detail="Вставь Cookie Editor JSON")
        account_id = str(uuid.uuid4())
        public_account = {
            "id": account_id,
            "owner_email": session["email"],
            "platform": "intCity",
            "name": payload.account_name or payload.intcity_email,
            "profile_url": f"mailto:{payload.intcity_email}",
            "final_url": f"mailto:{payload.intcity_email}",
            "photo_url": "/intcity_logo.png",
            "session_valid": True,
            "session_reason": "OK",
            "images_found": 0,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        # Парсим Cookie Editor JSON и тянем токен со страницы
        mail_cookie_str = ""
        mail_token = ""
        try:
            import httpx as _httpx, re as _re
            cookie_list = json.loads(payload.cookies_raw)
            mail_cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookie_list if c.get("name") and c.get("value"))
            print(f"[intCity] Собрано кук: {len(cookie_list)}", flush=True)
            page_resp = _httpx.get(
                "https://e.mail.ru/inbox/",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    "Cookie": mail_cookie_str,
                },
                timeout=15,
                follow_redirects=True,
            )
            token_match = _re.search(r'[a-f0-9]{32}:[A-Za-z0-9_\-+/=.]{20,}', page_resp.text)
            if token_match:
                mail_token = token_match.group(0)
                print(f"[intCity] Токен получен: {mail_token[:20]}...", flush=True)
            else:
                print(f"[intCity] Токен не найден в HTML", flush=True)
        except Exception as e:
            print(f"[intCity] Ошибка при парсинге кук: {e}", flush=True)

        cookies_raw = json.dumps({
            "email": "",
            "password": "",
            "mail_cookie": mail_cookie_str,
            "mail_token": mail_token,
        })
        supabase.table("accounts").insert(public_account).execute()
        supabase.table("accounts_private").insert({"id": account_id, "cookies_raw": cookies_raw}).execute()
        warning = None if mail_token else "Токен не получен автоматически — вставь вручную на карточке"
        return {"ok": True, "account": public_account, "warning": warning}

    raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform_lower}")

# ── Tasks — проксируем на воркеры ────────────────────────

def get_account_platform(account_id: str) -> str:
    """Получает платформу аккаунта из Supabase."""
    try:
        res = supabase.table("accounts").select("platform").eq("id", account_id).limit(1).execute()
        if res.data:
            return (res.data[0].get("platform") or "mamba").lower()
    except Exception:
        pass
    return "mamba"

@app.post("/api/tasks/likes-http")
async def api_task_likes(payload: LikesTaskRequest, authorization: str | None = Header(default=None)):
    platform = get_account_platform(payload.account_id)
    if platform == "lovelaz":
        return await proxy_to_worker("lovelaz", "/api/tasks/lovelaz-likes", payload.model_dump(), authorization)
    elif platform == "twinby":
        return await proxy_to_worker("twinby", "/api/tasks/twinby-likes", payload.model_dump(), authorization)
    elif platform == "vznakomstve":
        return await proxy_to_worker("vznakomstve", "/api/tasks/vznakomstve-likes", payload.model_dump(), authorization)
    else:
        return await proxy_to_worker("mamba", "/api/tasks/likes-http", payload.model_dump(), authorization)

@app.post("/api/tasks/lovelaz-likes")
async def api_task_lovelaz_likes(payload: LikesTaskRequest, authorization: str | None = Header(default=None)):
    return await proxy_to_worker("lovelaz", "/api/tasks/lovelaz-likes", payload.model_dump(), authorization)

@app.post("/api/tasks/auto-reply-http")
async def api_task_auto_reply(payload: AutoReplyTaskRequest, authorization: str | None = Header(default=None)):
    platform = get_account_platform(payload.account_id)
    if platform == "lovelaz":
        return await proxy_to_worker("lovelaz", "/api/tasks/lovelaz-auto-reply", payload.model_dump(), authorization)
    elif platform == "twinby":
        return await proxy_to_worker("twinby", "/api/tasks/twinby-auto-reply", payload.model_dump(), authorization)
    elif platform == "vznakomstve":
        return await proxy_to_worker("vznakomstve", "/api/tasks/vznakomstve-auto-reply", payload.model_dump(), authorization)
    else:
        return await proxy_to_worker("mamba", "/api/tasks/auto-reply-http", payload.model_dump(), authorization)

@app.post("/api/tasks/auto-reply-http-loop")
async def api_task_auto_reply_loop(payload: AutoReplyTaskRequest, authorization: str | None = Header(default=None)):
    platform = get_account_platform(payload.account_id)
    if platform == "lovelaz":
        return await proxy_to_worker("lovelaz", "/api/tasks/lovelaz-auto-reply", payload.model_dump(), authorization)
    elif platform == "twinby":
        return await proxy_to_worker("twinby", "/api/tasks/twinby-auto-reply", payload.model_dump(), authorization)
    elif platform == "vznakomstve":
        return await proxy_to_worker("vznakomstve", "/api/tasks/vznakomstve-auto-reply", payload.model_dump(), authorization)
    else:
        return await proxy_to_worker("mamba", "/api/tasks/auto-reply-http-loop", payload.model_dump(), authorization)

@app.post("/api/tasks/lovelaz-auto-reply")
async def api_task_lovelaz_auto_reply(payload: AutoReplyTaskRequest, authorization: str | None = Header(default=None)):
    return await proxy_to_worker("lovelaz", "/api/tasks/lovelaz-auto-reply", payload.model_dump(), authorization)

@app.post("/api/tasks/stop")
async def api_task_stop(payload: StopTaskRequest, authorization: str | None = Header(default=None)):
    # Стоп на всех воркерах одновременно
    async with httpx.AsyncClient(timeout=10) as client:
        for url in PLATFORM_URLS.values():
            try:
                await client.post(f"{url}/api/tasks/stop", json={"account_id": payload.account_id})
            except Exception:
                pass
    supabase.table("job_queue").update({"status": "cancelled"}).eq("account_id", payload.account_id).in_("status", ["pending", "running"]).execute()
    return {"ok": True}

# ── Twinby / Vznakomstve send-code ───────────────────────

@app.post("/api/twinby/send-code")
async def twinby_send_code(payload: dict, authorization: str | None = Header(default=None)):
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{TWINBY_SERVER_URL}/api/twinby/send-code", json=payload, headers={"Authorization": authorization or ""})
        return resp.json()

@app.post("/api/vznakomstve/send-code")
async def vzn_send_code(payload: dict, authorization: str | None = Header(default=None)):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{VZNAKOMSTVE_SERVER_URL}/api/vznakomstve/send-code", json=payload, headers={"Authorization": authorization or ""})
        return resp.json()

@app.post("/api/vznakomstve/verify-code")
async def vzn_verify_code(payload: dict, authorization: str | None = Header(default=None)):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{VZNAKOMSTVE_SERVER_URL}/api/vznakomstve/verify-code", json=payload, headers={"Authorization": authorization or ""})
        return resp.json()

# ── AI Settings ───────────────────────────────────────────

@app.get("/api/ai-settings/{account_id}")
def api_get_ai_settings(account_id: str, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    account_res = supabase.table("accounts").select("id").eq("id", account_id).in_("owner_email", owner_emails).execute()
    if not account_res.data:
        raise HTTPException(status_code=403, detail="Нет доступа")
    return {"ok": True, "settings": get_ai_settings(account_id)}

@app.post("/api/ai-settings/{account_id}")
def api_save_ai_settings(account_id: str, payload: AiSettingsPayload, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    account_res = supabase.table("accounts").select("id").eq("id", account_id).in_("owner_email", owner_emails).execute()
    if not account_res.data:
        raise HTTPException(status_code=403, detail="Нет доступа")
    existing = get_ai_settings(account_id)
    data = {k: v for k, v in payload.model_dump().items() if v != "" and v is not None}
    merged = {**existing, **data}
    saved = save_ai_settings(account_id, merged)
    return {"ok": True, "settings": saved}

# ── Tasks log / Stats ─────────────────────────────────────

@app.get("/api/tasks-log")
def api_tasks_log():
    res = supabase.table("tasks_log").select("*").order("created_at", desc=True).limit(200).execute()
    return {"ok": True, "logs": res.data or []}

@app.get("/api/accounts-stats")
def api_accounts_stats(authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    accounts_res = supabase.table("accounts").select("id").in_("owner_email", owner_emails).execute()
    account_ids = [a["id"] for a in (accounts_res.data or [])]
    if not account_ids:
        return {"ok": True, "stats": {}}
    res = supabase.table("tasks_log").select("account_id, type, liked, replied, contacts_sent").in_("account_id", account_ids).execute()
    stats: dict[str, dict] = {}
    for row in (res.data or []):
        acc_id = row.get("account_id")
        if not acc_id:
            continue
        if acc_id not in stats:
            stats[acc_id] = {"liked": 0, "replied": 0, "contacts": 0}
        if row.get("type") == "likes":
            stats[acc_id]["liked"] += int(row.get("liked") or 0)
        if row.get("type") == "auto-reply-http":
            stats[acc_id]["replied"] += int(row.get("replied") or 0)
            stats[acc_id]["contacts"] += int(row.get("contacts_sent") or 0)
    return {"ok": True, "stats": stats}

# ── Notifications ─────────────────────────────────────────

@app.get("/api/notifications")
def api_get_notifications(authorization: str | None = Header(default=None)):
    try:
        session = require_auth(authorization)
        res = supabase.table("notifications").select("*").eq("email", session["email"]).order("created_at", desc=True).limit(50).execute()
        return {"ok": True, "notifications": res.data or []}
    except Exception as e:
        return {"ok": False, "notifications": [], "error": str(e)}

# ── Team ──────────────────────────────────────────────────

@app.post("/api/team/invite")
def api_team_invite(payload: TeamInviteRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_email = session["email"].strip().lower()
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Некорректный email")
    if owner_email == email:
        raise HTTPException(status_code=400, detail="Нельзя пригласить самого себя")
    invite_res = supabase.table("team_invites").insert({"owner_email": owner_email, "email": email, "role": payload.role, "status": "pending"}).execute()
    invite = invite_res.data[0]
    supabase.table("notifications").insert({"email": email, "type": "team_invite", "title": "Приглашение в команду", "message": f"{owner_email} приглашает вас в команду", "data": {"invite_id": invite["id"], "owner_email": owner_email, "role": payload.role}, "is_read": False}).execute()
    return {"ok": True, "invite": invite}

@app.post("/api/team/invite/accept")
def api_accept_invite(payload: AcceptInviteRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    email = session["email"]
    res = supabase.table("team_invites").select("*").eq("id", payload.invite_id).eq("email", email).eq("status", "pending").execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    invite = res.data[0]
    supabase.table("team_members").upsert({"owner_email": invite["owner_email"], "member_email": email, "role": invite["role"], "status": "active"}).execute()
    supabase.table("team_invites").update({"status": "accepted", "accepted_at": datetime.now().isoformat()}).eq("id", payload.invite_id).execute()
    supabase.table("notifications").update({"is_read": True}).eq("email", email).eq("type", "team_invite").execute()
    return {"ok": True}

@app.post("/api/team/invite/reject")
def api_reject_invite(payload: RejectInviteRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    email = session["email"]
    supabase.table("team_invites").update({"status": "rejected"}).eq("id", payload.invite_id).eq("email", email).execute()
    supabase.table("notifications").update({"is_read": True}).eq("email", email).eq("type", "team_invite").execute()
    return {"ok": True}

@app.get("/api/team/members")
def api_team_members(authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    res = supabase.table("team_members").select("*").eq("owner_email", session["email"]).order("created_at", desc=True).execute()
    return {"ok": True, "members": res.data or []}

# ── Tabs ──────────────────────────────────────────────────

@app.get("/api/tabs")
def api_get_tabs(authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    res = supabase.table("operator_tabs").select("*").in_("owner_email", owner_emails).order("sort_order", desc=False).execute()
    tabs = res.data or []
    tab_ids = [t["id"] for t in tabs]
    tags_by_tab = {}
    if tab_ids:
        tags_res = supabase.table("account_tabs").select("*").in_("tab_id", tab_ids).execute()
        for row in tags_res.data or []:
            tags_by_tab.setdefault(row["tab_id"], []).append(row["account_id"])
    for t in tabs:
        t["account_ids"] = tags_by_tab.get(t["id"], [])
    return {"ok": True, "tabs": tabs}

@app.post("/api/tabs")
def api_create_tab(payload: CreateTabRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название вкладки не может быть пустым")
    count_res = supabase.table("operator_tabs").select("id").eq("owner_email", session["email"]).execute()
    res = supabase.table("operator_tabs").insert({"owner_email": session["email"], "name": name, "platform": payload.platform or "Mamba", "sort_order": len(count_res.data or [])}).execute()
    return {"ok": True, "tab": res.data[0]}

@app.delete("/api/tabs/{tab_id}")
def api_delete_tab(tab_id: str):
    supabase.table("operator_tabs").delete().eq("id", tab_id).execute()
    return {"ok": True}

@app.post("/api/tabs/assign")
def api_assign_tab(payload: AssignTabRequest):
    supabase.table("account_tabs").upsert({"account_id": payload.account_id, "tab_id": payload.tab_id}).execute()
    return {"ok": True}

@app.post("/api/tabs/unassign")
def api_unassign_tab(payload: AssignTabRequest):
    supabase.table("account_tabs").delete().eq("account_id", payload.account_id).eq("tab_id", payload.tab_id).execute()
    return {"ok": True}

# ── Split logs ────────────────────────────────────────────

@app.post("/api/split-log/push")
def api_split_log_push(payload: SplitLogPushRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    if not payload.messages:
        return {"ok": True}
    rows = [{"owner_email": session["email"], "account_id": payload.account_id, "message": msg} for msg in payload.messages if msg]
    supabase.table("split_logs").insert(rows).execute()
    return {"ok": True, "saved": len(rows)}

@app.get("/api/split-log/{account_id}")
def api_split_log_get(account_id: str, after_id: int = 0, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    if after_id > 0:
        query = supabase.table("split_logs").select("id, message, created_at").eq("account_id", account_id).gt("id", after_id).order("id", desc=False)
    else:
        query = supabase.table("split_logs").select("id, message, created_at").eq("account_id", account_id).order("id", desc=True).limit(200)
    res = query.execute()
    rows = res.data or []
    if after_id == 0:
        rows = list(reversed(rows))
    return {"ok": True, "logs": rows, "last_id": rows[-1]["id"] if rows else after_id}

# ── Proxy settings ────────────────────────────────────────

@app.get("/api/proxy-settings")
async def get_proxy_settings(authorization: str = Header(None)):
    require_auth(authorization)
    try:
        res = supabase.table("proxy_settings").select("*").execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/proxy-settings")
async def save_proxy_settings(body: ProxySettingsModel, authorization: str = Header(None)):
    require_auth(authorization)
    try:
        supabase.table("proxy_settings").upsert({
            "id": body.id, "host": body.host, "port": body.port,
            "username": body.username, "password": body.password,
            "use_proxy": body.use_proxy, "user_agent": body.user_agent,
            "updated_at": datetime.utcnow().isoformat(),
        }, on_conflict="id").execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Proxy image ───────────────────────────────────────────

@app.get("/api/proxy-image")
async def proxy_image(url: str, account_id: str = ""):
    from fastapi.responses import Response
    try:
        headers = {"User-Agent": "InDating v3.2.6 (302060), Android 9, A5010", "Referer": "https://vznakomstve.com/"}
        if "amazonaws.com" in url and account_id:
            try:
                res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
                if res.data:
                    raw = res.data[0].get("cookies_raw", "")
                    cookies_list = json.loads(raw)
                    for c in cookies_list:
                        if c.get("name") == "x_token":
                            headers["x-token"] = c["value"]
                            break
            except Exception:
                pass
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
        return Response(content=r.content, media_type=r.headers.get("content-type", "image/jpeg"))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

# ── Analytics cards ──────────────────────────────────────

class AnalyticsCardPayload(BaseModel):
    account_id: Optional[str] = None
    owner_email: Optional[str] = None
    platform: Optional[str] = None
    bot_name: str = ""
    bot_age: str = ""
    bot_gender: str = "female"
    location: str = ""
    persona: str = ""
    goal: str = ""
    stop_topics: str = ""
    contacts: str = ""
    contacts_trigger: str = ""

@app.get("/api/analytics-cards")
def api_get_analytics_cards(authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])
    accounts_res = supabase.table("accounts").select("id").in_("owner_email", owner_emails).execute()
    account_ids = [a["id"] for a in (accounts_res.data or []) if a.get("id")]
    cards_res = supabase.table("analytics_cards").select("*").in_("owner_email", owner_emails).execute()
    null_cards = [c for c in (cards_res.data or []) if c.get("account_id") is None]
    if account_ids:
        account_cards = supabase.table("analytics_cards").select("*").in_("account_id", account_ids).execute()
        all_cards = (account_cards.data or []) + null_cards
    else:
        all_cards = null_cards
    cards_res_data = all_cards
    settings_res = supabase.table("ai_settings").select("*").in_("account_id", account_ids).execute() if account_ids else type('obj', (object,), {'data': []})()
    settings_by_account = {s.get("account_id"): s for s in (settings_res.data or [])}
    result = []
    for card in cards_res_data:
        account_id = card.get("account_id", "")
        settings = settings_by_account.get(account_id) or {}
        result.append({
            "id": card.get("id", ""),
            "account_id": account_id,
            "platform": card.get("platform") or "Mamba",
            "bot_name": card.get("bot_name") or settings.get("bot_name") or "",
            "bot_age": card.get("bot_age") or settings.get("bot_age") or "",
            "bot_gender": card.get("bot_gender") or settings.get("bot_gender") or "female",
            "location": card.get("location") or settings.get("location") or "",
            "persona": card.get("persona") or settings.get("persona") or "",
            "goal": card.get("goal") or settings.get("goal") or "",
            "stop_topics": card.get("stop_topics") or settings.get("stop_topics") or "",
            "contacts": card.get("contacts") or settings.get("contacts") or "",
            "contacts_trigger": card.get("contacts_trigger") or settings.get("contacts_trigger") or "",
        })
    return {"ok": True, "cards": result}

@app.post("/api/analytics-cards")
def api_save_analytics_card(payload: AnalyticsCardPayload, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    data = payload.model_dump()
    data["id"] = str(uuid.uuid4())
    data["owner_email"] = session["email"]
    supabase.table("analytics_cards").insert(data).execute()
    return {"ok": True, "card": data}

@app.patch("/api/analytics-cards/{card_id}")
def api_update_analytics_card(card_id: str, payload: AnalyticsCardPayload):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    supabase.table("analytics_cards").update(data).eq("id", card_id).execute()
    return {"ok": True}

@app.delete("/api/analytics-cards/{card_id}")
def api_delete_analytics_card(card_id: str):
    supabase.table("analytics_cards").delete().eq("id", card_id).execute()
    return {"ok": True}

# ── Jobs ──────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str):
    if not job_id or job_id == "undefined":
        return {"ok": False, "job": None}
    res = supabase.table("job_queue").select("*").eq("id", job_id).execute()
    if not res.data:
        return {"ok": False, "job": None}
    return {"ok": True, "job": res.data[0]}

@app.get("/api/jobs/account/{account_id}/active")
def api_get_active_job(account_id: str):
    res = supabase.table("job_queue").select("*").eq("account_id", account_id).in_("status", ["pending", "running"]).order("created_at", desc=True).limit(1).execute()
    return {"ok": True, "job": res.data[0] if res.data else None}

# ── Tasks likes / broadcast ───────────────────────────────

@app.post("/api/tasks/likes")
async def api_task_likes_old(payload: LikesTaskRequest, authorization: str | None = Header(default=None)):
    platform = payload.platform.lower() if hasattr(payload, 'platform') else "mamba"
    return await proxy_to_worker(platform, "/api/tasks/likes-http", payload.model_dump(), authorization)

@app.post("/api/tasks/broadcast")
async def api_task_broadcast(payload: dict, authorization: str | None = Header(default=None)):
    return {"ok": True, "status": "not_implemented"}

# ── Chats ─────────────────────────────────────────────────

class SendChatMessageRequest(BaseModel):
    account_id: str
    href: str
    message: str

@app.post("/api/chats/send")
async def api_send_chat_message(payload: SendChatMessageRequest, authorization: str | None = Header(default=None)):
    return await proxy_to_worker("mamba", "/api/chats/send", payload.model_dump(), authorization)

@app.get("/api/chats/{account_id}")
async def api_get_chats(account_id: str):
    return {"ok": True, "chats": []}

# ── Sheet ─────────────────────────────────────────────────

class SheetCellPayload(BaseModel):
    sheet_id: str
    cells: list[dict]

class CheckKeysRequest(BaseModel):
    keys: list[str]

@app.post("/api/sheet/save")
def api_sheet_save(payload: SheetCellPayload, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    email = session["email"]
    if not payload.cells:
        return {"ok": True}
    rows = []
    for c in payload.cells:
        row = {"owner_email": email, "sheet_id": payload.sheet_id, "row_idx": int(c.get("row", 0)), "col_idx": int(c.get("col", 0)), "value": c.get("value", "")}
        if c.get("assigned_account_id"):
            row["assigned_account_id"] = c.get("assigned_account_id")
        rows.append(row)
    empty_rows = [r for r in rows if not r.get("value")]
    save_rows = [r for r in rows if r.get("value")]
    for er in empty_rows:
        supabase.table("sheet_cells").delete().eq("owner_email", email).eq("sheet_id", payload.sheet_id).eq("row_idx", er["row_idx"]).eq("col_idx", er["col_idx"]).execute()
    if save_rows:
        supabase.table("sheet_cells").upsert(save_rows, on_conflict="owner_email,sheet_id,row_idx,col_idx").execute()
    return {"ok": True, "saved": len(save_rows)}

@app.get("/api/sheet/load")
def api_sheet_load(sheet_id: str, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    res = supabase.table("sheet_cells").select("*").eq("owner_email", session["email"]).eq("sheet_id", sheet_id).execute()
    return {"ok": True, "cells": res.data or []}

@app.post("/api/sheet/check-keys")
def api_check_keys(payload: CheckKeysRequest, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    from shared import call_groq, is_key_exhausted
    results = {}
    for key in payload.keys:
        key = key.strip()
        if not key:
            continue
        try:
            call_groq(key, "llama-3.3-70b-versatile", "test", [{"role": "user", "content": "1"}])
            results[key] = "ok"
        except RuntimeError as e:
            results[key] = "exhausted" if is_key_exhausted(str(e)) else "error"
        except Exception:
            results[key] = "error"
    return {"ok": True, "results": results}

# ── Report ────────────────────────────────────────────────

class ReportTgAccountRequest(BaseModel):
    tg_username: str
    label: str = ""

class ReportEntryRequest(BaseModel):
    tg_account: str
    date: str
    visits: int = 0
    bookings: int = 0
    cancels: int = 0
    notes: str = ""

@app.get("/api/report/tg-accounts")
def api_report_tg_accounts_get(authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    res = supabase.table("report_tg_accounts").select("*").eq("owner_email", session["email"]).order("created_at").execute()
    return {"ok": True, "accounts": res.data or []}

@app.post("/api/report/tg-accounts")
def api_report_tg_accounts_post(payload: ReportTgAccountRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    username = payload.tg_username.lstrip("@").strip()
    if not username:
        raise HTTPException(status_code=400, detail="tg_username обязателен")
    try:
        res = supabase.table("report_tg_accounts").insert({"owner_email": session["email"], "tg_username": username, "label": payload.label}).execute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "account": res.data[0] if res.data else {}}

@app.delete("/api/report/tg-accounts/{account_id}")
def api_report_tg_accounts_delete(account_id: str, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    supabase.table("report_tg_accounts").delete().eq("id", account_id).eq("owner_email", session["email"]).execute()
    return {"ok": True}

@app.get("/api/report/entries")
def api_report_entries_get(month: str, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    try:
        year, mon = month.split("-")
        date_from = f"{year}-{mon}-01"
        next_mon = int(mon) + 1
        next_year = int(year)
        if next_mon > 12:
            next_mon = 1
            next_year += 1
        date_to = f"{next_year}-{next_mon:02d}-01"
    except Exception:
        raise HTTPException(status_code=400, detail="month должен быть в формате YYYY-MM")
    res = supabase.table("report_entries").select("*").eq("owner_email", session["email"]).gte("date", date_from).lt("date", date_to).order("date").execute()
    return {"ok": True, "entries": res.data or []}

@app.post("/api/report/entries")
def api_report_entries_post(payload: ReportEntryRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    try:
        res = supabase.table("report_entries").upsert({"owner_email": session["email"], "tg_account": payload.tg_account, "date": payload.date, "visits": payload.visits, "bookings": payload.bookings, "cancels": payload.cancels, "notes": payload.notes, "updated_at": datetime.utcnow().isoformat()}, on_conflict="owner_email,tg_account,date").execute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "entry": res.data[0] if res.data else {}}

@app.get("/api/report/summary")
def api_report_summary(month: str, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    try:
        year, mon = month.split("-")
        date_from = f"{year}-{mon}-01"
        next_mon = int(mon) + 1
        next_year = int(year)
        if next_mon > 12:
            next_mon = 1
            next_year += 1
        date_to = f"{next_year}-{next_mon:02d}-01"
    except Exception:
        raise HTTPException(status_code=400, detail="month должен быть в формате YYYY-MM")
    tg_res = supabase.table("report_tg_accounts").select("*").eq("owner_email", session["email"]).execute()
    entries_res = supabase.table("report_entries").select("*").eq("owner_email", session["email"]).gte("date", date_from).lt("date", date_to).execute()
    entries_map = {(e["tg_account"], e["date"]): e for e in (entries_res.data or [])}
    from datetime import date as dt_date, timedelta
    start = dt_date(int(year), int(mon), 1)
    days = []
    cur = start
    while cur.month == start.month:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    rows = []
    for day in days:
        for acc in (tg_res.data or []):
            username = acc["tg_username"].lstrip("@").lower()
            entry = entries_map.get((acc["tg_username"], day), entries_map.get((username, day), {}))
            rows.append({"date": day, "tg_account": acc["tg_username"], "label": acc.get("label", ""), "leads": 0, "visits": entry.get("visits", 0) or 0, "bookings": entry.get("bookings", 0) or 0, "cancels": entry.get("cancels", 0) or 0, "conversion": 0.0})
    return {"ok": True, "rows": rows, "month": month}

# ── Groq error ────────────────────────────────────────────

@app.get("/api/groq-error")
def api_get_groq_error():
    return {"ok": True, "error": None}

@app.post("/api/groq-error/dismiss")
def api_dismiss_groq_error():
    return {"ok": True}

class IntCitySplitRequest(BaseModel):
    account_id: str
    pages: int = 3
    subject: str = ""
    body: str = ""
    mail_cookie: str = ""
    mail_token: str = ""

@app.post("/api/tasks/intcity-split")
async def intcity_split_task(payload: IntCitySplitRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    # Сохраняем subject/body в ai_settings
    existing = supabase.table("ai_settings").select("account_id").eq("account_id", payload.account_id).execute()
    settings_data = {
        "goal": payload.subject,
        "persona": payload.body,
        "bot_age": str(payload.pages),
    }
    if payload.mail_cookie:
        settings_data["gemini_api_keys"] = payload.mail_cookie
    if payload.mail_token:
        settings_data["stop_topics"] = payload.mail_token
    try:
        if existing.data:
            supabase.table("ai_settings").update(settings_data).eq("account_id", payload.account_id).execute()
        else:
            settings_data["account_id"] = payload.account_id
            supabase.table("ai_settings").insert(settings_data).execute()
    except Exception as e:
        print(f"[intCity] ai_settings save error: {e}", flush=True)
    # Создаём задачу в job_queue
    job = {
        "account_id": payload.account_id,
        "platform": "intCity",
        "type": "intcity-split",
        "status": "pending",
        "payload": {"pages": payload.pages},
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    supabase.table("job_queue").insert(job).execute()
    return {"ok": True, "summary": "Задача создана"}

# ── intCity: парсер и рассылка ────────────────────────────

import re as _re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class IntCityParseRequest(BaseModel):
    account_id: str
    pages: int = 3

class IntCitySendRequest(BaseModel):
    account_id: str
    subject: str
    body: str
    limit: int = 50

@app.post("/api/intcity/parse")
async def intcity_parse(payload: IntCityParseRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    priv = supabase.table("accounts_private").select("cookies_raw").eq("id", payload.account_id).execute()
    if not priv.data:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    owner_email = session["email"]

    BASE_URL = "https://a.intimcity.co"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    found_emails = []
    errors = []
    ad_urls = []

    async with httpx.AsyncClient(headers=headers, timeout=20, follow_redirects=True) as client:
        for page in range(1, payload.pages + 1):
            try:
                url = f"{BASE_URL}/bullboard?gender_from=m&gender_to=f&place=&page={page}"
                resp = await client.get(url)
                links = _re.findall(r'href="(/bullboard/\d+)"', resp.text)
                for link in links:
                    full = BASE_URL + link
                    if full not in ad_urls:
                        ad_urls.append(full)
            except Exception as e:
                errors.append(f"Страница {page}: {e}")

        for ad_url in ad_urls:
            try:
                resp = await client.get(ad_url)
                emails = _re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', resp.text)
                emails = [e for e in emails if not any(x in e for x in ["intimcity", "example", "test"])]
                for email in set(emails):
                    found_emails.append({"email": email, "ad_url": ad_url})
            except Exception as e:
                errors.append(f"{ad_url}: {e}")

    saved = 0
    for item in found_emails:
        try:
            supabase.table("intcity_leads").upsert({
                "email": item["email"],
                "ad_url": item["ad_url"],
                "owner_email": owner_email,
            }, on_conflict="email").execute()
            saved += 1
        except Exception:
            pass

    return {
        "ok": True,
        "found": len(found_emails),
        "saved": saved,
        "ads_parsed": len(ad_urls),
        "errors": errors[:10],
        "summary": f"Найдено {len(found_emails)} email, сохранено {saved}, объявлений: {len(ad_urls)}"
    }


@app.get("/api/intcity/leads")
async def intcity_leads(account_id: str, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    res = supabase.table("intcity_leads").select("*").eq("owner_email", session["email"]).order("created_at", desc=True).limit(500).execute()
    return {"ok": True, "leads": res.data or []}


@app.post("/api/intcity/send")
async def intcity_send(payload: IntCitySendRequest, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    priv = supabase.table("accounts_private").select("cookies_raw").eq("id", payload.account_id).execute()
    if not priv.data:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    creds = json.loads(priv.data[0]["cookies_raw"])
    sender_email = creds["email"]
    sender_password = creds["password"]

    res = supabase.table("intcity_leads").select("*").eq("owner_email", session["email"]).is_("sent_at", "null").limit(payload.limit).execute()
    leads = res.data or []

    if not leads:
        return {"ok": True, "sent": 0, "summary": "Нет новых лидов для рассылки"}

    sent = 0
    errors = []

    try:
        smtp = smtplib.SMTP_SSL("smtp.mail.ru", 465)
        smtp.login(sender_email, sender_password)
        for lead in leads:
            try:
                msg = MIMEMultipart()
                msg["From"] = sender_email
                msg["To"] = lead["email"]
                msg["Subject"] = payload.subject
                msg.attach(MIMEText(payload.body, "plain", "utf-8"))
                smtp.sendmail(sender_email, lead["email"], msg.as_string())
                supabase.table("intcity_leads").update({
                    "sent_at": datetime.now().isoformat()
                }).eq("id", lead["id"]).execute()
                sent += 1
            except Exception as e:
                errors.append(f"{lead['email']}: {e}")
        smtp.quit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка SMTP: {e}")

    return {
        "ok": True,
        "sent": sent,
        "errors": errors[:10],
        "summary": f"Отправлено {sent} из {len(leads)}"
    }

# ── Key Slots ─────────────────────────────────────────────

class KeySlotPayload(BaseModel):
    name: str = "Слот"
    keys: str = ""

class ProxyCheckRequest(BaseModel):
    protocol: str = "http"
    host: str = ""
    port: str = ""
    login: str = ""
    password: str = ""

class ProxyCheckUARequest(BaseModel):
    protocol: str = "http"
    host: str = ""
    port: str = ""
    login: str = ""
    password: str = ""
    user_agent: str = ""

@app.post("/api/proxy/check-ua")
def api_proxy_check_ua(payload: ProxyCheckUARequest, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    return {"ok": True, "user_agent": payload.user_agent or "не задан"}

@app.post("/api/proxy/check")
def api_proxy_check(payload: ProxyCheckRequest, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    try:
        proxy_url = f"{payload.protocol}://"
        if payload.login and payload.password:
            proxy_url += f"{payload.login}:{payload.password}@"
        proxy_url += f"{payload.host}:{payload.port}"
        import httpx as _httpx
        try:
            with _httpx.Client(proxy=proxy_url, timeout=10) as client:
                r = client.get("https://api.ipify.org?format=json")
                data = r.json()
                return {"ok": True, "ip": data.get("ip", "")}
        except TypeError:
            with _httpx.Client(proxies={"all://": proxy_url}, timeout=10) as client:
                r = client.get("https://api.ipify.org?format=json")
                data = r.json()
                return {"ok": True, "ip": data.get("ip", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}

@app.get("/api/key-slots")
def api_get_key_slots(authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    res = supabase.table("key_slots").select("*").eq("owner_email", session["email"]).order("created_at").execute()
    return {"ok": True, "slots": res.data or []}

@app.post("/api/key-slots")
def api_create_key_slot(payload: KeySlotPayload, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    res = supabase.table("key_slots").insert({
        "owner_email": session["email"],
        "name": payload.name,
        "keys": payload.keys,
    }).execute()
    return {"ok": True, "slot": res.data[0]}

@app.patch("/api/key-slots/{slot_id}")
def api_update_key_slot(slot_id: str, payload: KeySlotPayload, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    res = supabase.table("key_slots").update({
        "name": payload.name,
        "keys": payload.keys,
    }).eq("id", slot_id).eq("owner_email", session["email"]).execute()

    # Если слот уже привязан к анкете — прокидываем обновлённые ключи в ai_settings
    if res.data:
        slot = res.data[0]
        account_id = slot.get("account_id")
        if account_id:
            keys = [k.strip() for k in (payload.keys or "").splitlines() if k.strip()]
            supabase.table("ai_settings").update({
                "groq_api_keys": "\n".join(keys)
            }).eq("account_id", account_id).execute()

    return {"ok": True}

@app.post("/api/key-slots/release/{account_id}")
def api_release_key_slot(account_id: str, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    # Находим слот привязанный к этой анкете и освобождаем его
    res = supabase.table("key_slots").select("*").eq("account_id", account_id).eq("owner_email", session["email"]).execute()
    if res.data:
        supabase.table("key_slots").update({"account_id": None}).eq("id", res.data[0]["id"]).execute()
    return {"ok": True}

@app.delete("/api/key-slots/{slot_id}")
def api_delete_key_slot(slot_id: str, authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    supabase.table("key_slots").delete().eq("id", slot_id).eq("owner_email", session["email"]).execute()
    return {"ok": True}

@app.post("/api/key-slots/{slot_id}/assign")
def api_assign_key_slot(slot_id: str, account_id: str = "", authorization: str | None = Header(default=None)):
    session = require_auth(authorization)
    owner_emails = get_team_owner_emails(session["email"])

    slot_res = supabase.table("key_slots").select("*").eq("id", slot_id).eq("owner_email", session["email"]).execute()
    if not slot_res.data:
        raise HTTPException(status_code=404, detail="Слот не найден")
    slot = slot_res.data[0]
    keys = [k.strip() for k in (slot["keys"] or "").splitlines() if k.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="Слот пустой")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id не передан")

    # Проверяем, что анкета принадлежит именно этому пользователю (или его команде)
    account_res = supabase.table("accounts").select("id").eq("id", account_id).in_("owner_email", owner_emails).execute()
    if not account_res.data:
        raise HTTPException(status_code=403, detail="Нет доступа к этой анкете")

    # Применяем все ключи к ai_settings анкеты
    existing = supabase.table("ai_settings").select("account_id").eq("account_id", account_id).execute()
    if existing.data:
        supabase.table("ai_settings").update({"groq_api_keys": "\n".join(keys)}).eq("account_id", account_id).execute()
    else:
        supabase.table("ai_settings").insert({"account_id": account_id, "groq_api_keys": "\n".join(keys)}).execute()
    # Привязываем слот к анкете
    supabase.table("key_slots").update({"account_id": account_id}).eq("id", slot_id).execute()
    return {"ok": True, "assigned": 1}

# ── Health ────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "service": "api"}

@app.head("/health")
def health_head():
    return {"ok": True}

# ── Auto cleanup split_logs ───────────────────────────────

async def cleanup_split_logs():
    """Чистит split_logs и tasks_log каждый час."""
    while True:
        try:
            await asyncio.sleep(3600)
            # Чистим split_logs — оставляем последние 20 на аккаунт
            res = supabase.table("split_logs").select("account_id").execute()
            account_ids = list(set(r["account_id"] for r in (res.data or [])))
            for acc_id in account_ids:
                keep = supabase.table("split_logs").select("id").eq("account_id", acc_id).order("id", desc=True).limit(20).execute()
                keep_ids = [r["id"] for r in (keep.data or [])]
                if keep_ids:
                    supabase.table("split_logs").delete().eq("account_id", acc_id).not_.in_("id", keep_ids).execute()
            print("[CLEANUP] split_logs очищен", flush=True)

            # Чистим tasks_log — оставляем последние 100 записей всего
            keep_tasks = supabase.table("tasks_log").select("id").order("id", desc=True).limit(100).execute()
            keep_task_ids = [r["id"] for r in (keep_tasks.data or [])]
            if keep_task_ids:
                supabase.table("tasks_log").delete().not_.in_("id", keep_task_ids).execute()
            print("[CLEANUP] tasks_log очищен", flush=True)

        except Exception as e:
            print(f"[CLEANUP] Ошибка: {e}", flush=True)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_split_logs())

# ── Static files ──────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")

@app.head("/")
def index_head():
    from fastapi.responses import Response
    return Response(status_code=200)

app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
app.mount("/", StaticFiles(directory=BASE_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
