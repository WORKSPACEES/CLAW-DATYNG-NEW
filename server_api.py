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
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request, error
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
TWINBY_SERVER_URL     = "https://claw-datyng-new-gu8x.onrender.com"
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
    """Проксирует запрос на нужный воркер-сервер."""
    base_url = PLATFORM_URLS.get(platform.lower())
    if not base_url:
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform}")
    
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{base_url}{path}", json=payload, headers=headers)
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Воркер {platform} недоступен")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
def delete_account(account_id: str):
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

    # Проксируем на нужный воркер для подключения
    worker_url = PLATFORM_URLS.get(platform_lower)
    if not worker_url:
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform_lower}")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{worker_url}/api/connect",
                json=payload.model_dump(),
                headers={"Authorization": authorization or ""}
            )
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Воркер {platform_lower} недоступен")

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
    async with httpx.AsyncClient(timeout=30) as client:
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
def api_get_ai_settings(account_id: str):
    return {"ok": True, "settings": get_ai_settings(account_id)}

@app.post("/api/ai-settings/{account_id}")
def api_save_ai_settings(account_id: str, payload: AiSettingsPayload):
    saved = save_ai_settings(account_id, payload.model_dump())
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
    account_id: str
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
    if not account_ids:
        return {"ok": True, "cards": []}
    cards_res = supabase.table("analytics_cards").select("*").in_("account_id", account_ids).execute()
    settings_res = supabase.table("ai_settings").select("*").in_("account_id", account_ids).execute()
    settings_by_account = {s.get("account_id"): s for s in (settings_res.data or [])}
    result = []
    for card in (cards_res.data or []):
        account_id = card.get("account_id", "")
        settings = settings_by_account.get(account_id) or {}
        result.append({
            "id": card.get("id", ""),
            "account_id": account_id,
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
def api_save_analytics_card(payload: AnalyticsCardPayload):
    data = payload.model_dump()
    data["id"] = str(uuid.uuid4())
    supabase.table("analytics_cards").insert(data).execute()
    return {"ok": True, "card": data}

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

# ── Health ────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "service": "api"}

# ── Static files ──────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")

app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
app.mount("/", StaticFiles(directory=BASE_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
