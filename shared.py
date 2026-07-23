# shared.py — общий код для всех микросерверов CLAW-DATYNG
import json
import os
import re
import secrets
import threading
import time
import uuid
import unicodedata
import http.client
from datetime import datetime
from pathlib import Path
from typing import Any

import bcrypt
import httpx
from supabase import create_client, Client
from supabase.client import ClientOptions

# ── Supabase ──────────────────────────────────────────────

SUPABASE_URL = "https://tbgaahpybvmfmzddrrdv.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRiZ2FhaHB5YnZtZm16ZGRycmR2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDkzMDksImV4cCI6MjA5NzE4NTMwOX0.mnF7po7rusq3XrDIdfTuzuK8vXVkpMkJRWWT7QVVf2c"

_supabase_http_client = httpx.Client(http2=False, timeout=30.0)
supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=ClientOptions(httpx_client=_supabase_http_client),
)

LEADS_SUPABASE_URL = "https://uspjqgjxtyllcincpumv.supabase.co"
LEADS_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVzcGpxZ2p4dHlsbGNpbmNwdW12Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA2NTQ3OTIsImV4cCI6MjA5NjIzMDc5Mn0.hsiEyMr1uLRDCqRxZaout8W_tzi-T3vlRypD6P9LmLM"

_leads_http_client = httpx.Client(http2=False, timeout=30.0)
leads_supabase: Client = create_client(
    LEADS_SUPABASE_URL,
    LEADS_SUPABASE_KEY,
    options=ClientOptions(httpx_client=_leads_http_client),
)

TELEGRAM_BOT_TOKEN = "8743731775:AAE3jy3zZOTaM8rYXie7LHmgfXduV9IY06g"
ACCESS_CODE = "VIPDATYNG3906"

# ── Paths ─────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── Auth ──────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False

def create_session(user_id: str, email: str) -> str:
    token = secrets.token_urlsafe(32)
    supabase.table("app_sessions").insert({
        "token": token,
        "user_id": user_id,
        "email": email,
    }).execute()
    return token

def get_session(token: str) -> dict | None:
    try:
        res = supabase.table("app_sessions").select("*").eq("token", token).execute()
        if not res.data:
            return None
        row = res.data[0]
        return {"user_id": row.get("user_id"), "email": row.get("email")}
    except Exception as e:
        print("get_session error:", repr(e))
        return None

def require_auth(authorization: str | None) -> dict:
    from fastapi import HTTPException
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Не авторизован")
    token = authorization[len("Bearer "):].strip()
    session = get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    return session

# ── Team helpers ──────────────────────────────────────────

def get_team_owner_emails(email: str) -> list[str]:
    owner_emails = {email}
    member_res = supabase.table("team_members").select("owner_email").eq("member_email", email).eq("status", "active").execute()
    for row in member_res.data or []:
        owner_emails.add(row["owner_email"])
    owned_team_res = supabase.table("team_members").select("member_email").eq("owner_email", email).eq("status", "active").execute()
    for row in owned_team_res.data or []:
        owner_emails.add(row["member_email"])
    return list(owner_emails)

# ── AI Settings ───────────────────────────────────────────

def default_ai_settings() -> dict:
    return {
        "groq_api_key": "", "groq_api_keys": "", "groq_model": "llama-3.3-70b-versatile",
        "bot_name": "", "bot_age": "", "bot_gender": "female", "location": "",
        "persona": "", "goal": "", "stop_topics": "", "contacts": "",
        "contacts_trigger": "", "tg_chat_id": "", "gemini_api_keys": "", "updated_at": None,
    }

def get_ai_settings(account_id: str) -> dict:
    res = supabase.table("ai_settings").select("*").eq("account_id", account_id).execute()
    if res.data:
        return {**default_ai_settings(), **res.data[0]}
    return default_ai_settings()

def save_ai_settings(account_id: str, payload: dict) -> dict:
    merged = {**default_ai_settings(), **payload, "account_id": account_id, "updated_at": datetime.now().isoformat()}
    existing = supabase.table("ai_settings").select("account_id").eq("account_id", account_id).execute()
    if existing.data:
        supabase.table("ai_settings").update(merged).eq("account_id", account_id).execute()
    else:
        supabase.table("ai_settings").insert(merged).execute()
    return merged

def get_groq_keys(settings: dict) -> list[str]:
    multi = (settings.get("groq_api_keys") or "").strip()
    if multi:
        return [k.strip() for k in multi.splitlines() if k.strip()]
    single = (settings.get("groq_api_key") or "").strip()
    return [single] if single else []

def get_gemini_keys(settings: dict) -> list[str]:
    multi = (settings.get("gemini_api_keys") or "").strip()
    return [k.strip() for k in multi.splitlines() if k.strip()]

# ── Groq / Gemini ─────────────────────────────────────────

_groq_key_index: dict[str, int] = {}
_groq_key_exhausted_at: dict[str, float] = {}
GROQ_KEY_COOLDOWN_SECONDS = 24 * 60 * 60
_groq_key_reset_date: str = ""

def _reset_groq_keys_if_new_day():
    global _groq_key_index, _groq_key_reset_date
    today = datetime.now().strftime("%Y-%m-%d")
    if _groq_key_reset_date != today:
        _groq_key_reset_date = today
        _groq_key_index = {}

def is_key_exhausted(error_msg: str) -> bool:
    msg = (error_msg or "").lower()
    return any(w in msg for w in [
        "rate_limit", "rate limit", "quota", "exceeded", "limit reached", "429",
        "restricted", "invalid api key", "invalid_api_key", "401", "403",
        "forbidden", "account is", "disabled",
    ])

def _has_foreign_script(text: str) -> bool:
    for ch in text:
        if ch.isspace() or not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        if not (name.startswith("CYRILLIC") or name.startswith("LATIN")):
            return True
    return False

def _strip_foreign_script(text: str) -> str:
    result = []
    for ch in text:
        if ch.isalpha():
            try:
                name = unicodedata.name(ch)
            except ValueError:
                result.append(ch)
                continue
            if name.startswith("CYRILLIC") or name.startswith("LATIN"):
                result.append(ch)
        else:
            result.append(ch)
    return re.sub(r"\s{2,}", " ", "".join(result)).strip()

def call_groq(api_key: str, model: str, system_prompt: str, messages: list[dict]) -> str:
    if not api_key:
        raise ValueError("Groq API ключ не задан")
    payload = json.dumps({
        "model": model or "llama-3.1-8b-instant",
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "temperature": 0.8,
        "max_completion_tokens": 80,
    }, ensure_ascii=False).encode("utf-8")
    conn = http.client.HTTPSConnection("api.groq.com", timeout=30)
    try:
        conn.request("POST", "/openai/v1/chat/completions", body=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Length": str(len(payload)),
        })
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="ignore")
    finally:
        conn.close()
    data = json.loads(body)
    if resp.status >= 400:
        err_msg = (data.get("error") or {}).get("message") or f"Groq error {resp.status}"
        raise RuntimeError(err_msg)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if _has_foreign_script(content):
        content = _strip_foreign_script(content)
    if len(content) < 2 or content in [".", ",", "!", "?", "-", "—"]:
        return ""
    return content

def call_gemini(api_key: str, system_prompt: str, messages: list[dict]) -> str:
    contents = []
    contents.append({"role": "user", "parts": [{"text": system_prompt}]})
    contents.append({"role": "model", "parts": [{"text": "Поняла, буду следовать инструкциям."}]})
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    payload = json.dumps({
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 80, "temperature": 0.8},
    }, ensure_ascii=False).encode("utf-8")
    conn = http.client.HTTPSConnection("generativelanguage.googleapis.com", timeout=30)
    try:
        conn.request("POST", f"/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
                     body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="ignore")
    finally:
        conn.close()
    data = json.loads(body)
    if resp.status >= 400:
        err = (data.get("error") or {}).get("message") or f"Gemini error {resp.status}"
        raise RuntimeError(f"Gemini: {err}")
    try:
        content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return ""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if _has_foreign_script(content):
        content = _strip_foreign_script(content)
    if len(content) < 2:
        return ""
    return content

def call_gemini_with_rotation(account_id: str, settings: dict, system_prompt: str, messages: list[dict]) -> str:
    keys = get_gemini_keys(settings)
    if not keys:
        raise RuntimeError("Gemini ключи не заданы")
    _gemini_key_index = getattr(call_gemini_with_rotation, "_index", {})
    start = _gemini_key_index.get(account_id, 0) % len(keys)
    _gemini_key_index[account_id] = start
    call_gemini_with_rotation._index = _gemini_key_index
    for attempt in range(len(keys)):
        idx = _gemini_key_index[account_id] % len(keys)
        key = keys[idx]
        try:
            return call_gemini(key, system_prompt, messages)
        except RuntimeError as e:
            if is_key_exhausted(str(e)):
                _gemini_key_index[account_id] = (idx + 1) % len(keys)
                continue
            raise
    raise RuntimeError("Все Gemini ключи исчерпаны")

def call_groq_with_rotation(account_id: str, settings: dict, system_prompt: str, messages: list[dict]) -> str:
    _reset_groq_keys_if_new_day()
    keys = get_groq_keys(settings)
    if not keys:
        gemini_keys = get_gemini_keys(settings)
        if gemini_keys:
            return call_gemini_with_rotation(account_id, settings, system_prompt, messages)
        raise ValueError("Не заданы ни Groq, ни Gemini API ключи")
    model = settings.get("groq_model") or "llama-3.3-70b-versatile"
    if account_id not in _groq_key_index:
        _groq_key_index[account_id] = 0
    for attempt in range(len(keys)):
        now = time.time()
        for k in list(_groq_key_exhausted_at.keys()):
            if now - _groq_key_exhausted_at[k] >= GROQ_KEY_COOLDOWN_SECONDS:
                del _groq_key_exhausted_at[k]
        idx = _groq_key_index[account_id] % len(keys)
        key = keys[idx]
        skipped = 0
        while key in _groq_key_exhausted_at and skipped < len(keys):
            _groq_key_index[account_id] = (idx + 1) % len(keys)
            idx = _groq_key_index[account_id]
            key = keys[idx]
            skipped += 1
        try:
            return call_groq(key, model, system_prompt, messages)
        except RuntimeError as e:
            if is_key_exhausted(str(e)):
                _groq_key_exhausted_at[key] = time.time()
                _groq_key_index[account_id] = (idx + 1) % len(keys)
                continue
            raise
    gemini_keys = get_gemini_keys(settings)
    if gemini_keys:
        return call_gemini_with_rotation(account_id, settings, system_prompt, messages)
    raise RuntimeError(f"Все {len(keys)} Groq API ключей исчерпаны")

# ── System prompt ─────────────────────────────────────────

def build_system_prompt(s: dict) -> str:
    gender = s.get("bot_gender", "female")
    gender_word = "девушка" if gender == "female" else "парень"
    name = (s.get("bot_name") or "").strip()
    age = (s.get("bot_age") or "").strip()
    location = (s.get("location") or "").strip()
    persona = (s.get("persona") or "").strip()
    goal = (s.get("goal") or "").strip()
    stop_topics = (s.get("stop_topics") or "").strip()
    contact = (s.get("contacts") or "").strip()
    contact_enabled = bool(contact and s.get("contacts_trigger"))

    identity = [f"Ты реальная живая {gender_word} на сайте знакомств."]
    if name:
        identity.append(f"Тебя зовут {name}.")
    if age:
        identity.append(f"Тебе {age} лет.")
    parts = [" ".join(identity)]

    if location:
        city = location.split(",")[0].strip()
        parts.append(f"ЛОКАЦИЯ: {location}. На 'откуда/какой город/где живёшь' отвечай только '{city}'.")

    if persona:
        parts.append(f"ХАРАКТЕР И СТИЛЬ: {persona}")
    if goal:
        parts.append(f"ЦЕЛЬ: {goal}")
    if stop_topics:
        parts.append(f"НЕ ОБСУЖДАЙ: {stop_topics}")

    if contact_enabled:
        parts.append(
            f"ТЕЛЕГРАМ: твой точный контакт — {contact}. "
            "Давай его сразу, если человек просит тг/контакт; предлагает встречу; "
            "сам прислал контакт; просит фото; спрашивает цену, условия или что входит. "
            f"Формат: 'лови тг {contact}, там спишемся'."
        )

    parts.append(
        f"""ПРАВИЛА ОТВЕТА:
- Отвечай только на последнее сообщение с учётом истории.
- Пиши как обычная {gender_word}: 1 короткое предложение, максимум 2.
- Никаких списков, заголовков, официальной речи.
- Не начинай с имени. Без эмодзи если не в стиле персонажа.
- На комплимент отвечай легко; на грубость — холодно; на интимный намёк — игриво.
- Если не поняла вопрос: 'не поняла)' или 'это как?'."""
    )

    return "\n\n".join(parts)

# ── Task log ──────────────────────────────────────────────

def append_task_log(entry: dict) -> dict:
    record = {
        "id": f"task_{uuid.uuid4().hex[:12]}",
        "created_at": datetime.now().isoformat(),
        "account_id": entry.get("account_id"),
        "type": entry.get("type"),
        "liked": int(entry.get("liked") or 0),
        "skipped": int(entry.get("skipped") or 0),
        "errors": int(entry.get("errors") or 0),
        "replied": int(entry.get("replied") or 0),
        "greeted": int(entry.get("greeted") or 0),
        "contacts_sent": int(entry.get("contacts_sent") or 0),
        "sent": int(entry.get("sent") or 0),
        "failed": int(entry.get("failed") or 0),
        "summary": entry.get("summary", ""),
    }
    try:
        supabase.table("tasks_log").insert(record).execute()
    except Exception as e:
        print("[TASK_LOG] Ошибка записи:", repr(e), flush=True)
    return record

# ── Block / Chain ─────────────────────────────────────────

def mark_account_blocked(account_id: str) -> dict:
    try:
        supabase.table("accounts").update({
            "is_blocked": True,
            "blocked_at": datetime.now().isoformat(),
            "block_reason": "Profile blocked or photo confirmation required",
            "run_status": "idle",
            "run_task": "",
            "run_note": "Анкета заблокирована",
        }).eq("id", account_id).execute()
        print(f"[BLOCKED] Анкета {account_id} отмечена заблокированной", flush=True)
        return {"ok": False, "reserve_account_id": None, "reason": "blocked"}
    except Exception as e:
        print(f"[BLOCKED] Ошибка: {e}", flush=True)
        return {"ok": False, "reserve_account_id": None, "reason": str(e)}

# ── Telegram ──────────────────────────────────────────────

def normalize_telegram(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^(?:https?://)?(?:www\.)?(?:t\.me/|telegram\.me/)", "", value)
    return value.lstrip("@").rstrip("/").strip()

def telegram_was_sent(user_id: str, telegram: str) -> bool:
    telegram = normalize_telegram(telegram)
    if not user_id or not telegram:
        return False
    result = supabase.table("telegram_delivery_log").select("id").eq("platform", "mamba").eq("user_id", str(user_id)).eq("telegram", telegram).limit(1).execute()
    return bool(result.data)

def reserve_telegram_send(user_id: str, telegram: str, account_id: str) -> bool:
    telegram = normalize_telegram(telegram)
    try:
        supabase.table("telegram_delivery_log").insert({
            "platform": "mamba",
            "user_id": str(user_id),
            "telegram": telegram,
            "account_id": str(account_id),
        }).execute()
        return True
    except Exception as exc:
        error_text = str(exc).lower()
        if "23505" in error_text or "duplicate" in error_text:
            return False
        raise

def cancel_telegram_reservation(user_id: str, telegram: str, account_id: str):
    telegram = normalize_telegram(telegram)
    supabase.table("telegram_delivery_log").delete().eq("platform", "mamba").eq("user_id", str(user_id)).eq("telegram", telegram).eq("account_id", str(account_id)).execute()

# ── Cancel flags ──────────────────────────────────────────

CANCEL_FLAGS: dict[str, bool] = {}
ACTIVE_JOB_IDS: dict[str, str] = {}

def should_cancel(account_id: str) -> bool:
    if CANCEL_FLAGS.get(account_id, False):
        return True
    job_id = ACTIVE_JOB_IDS.get(account_id)
    if not job_id:
        return False
    try:
        res = supabase.table("job_queue").select("status").eq("id", job_id).limit(1).execute()
        return bool(res.data and res.data[0].get("status") == "cancelled")
    except Exception:
        return False

def push_split_log_sync(account_id: str, message: str):
    try:
        owner_res = supabase.table("accounts").select("owner_email").eq("id", account_id).limit(1).execute()
        owner_email = owner_res.data[0].get("owner_email") if owner_res.data else ""
        supabase.table("split_logs").insert({
            "owner_email": owner_email or "",
            "account_id": account_id,
            "message": message,
        }).execute()
    except Exception as e:
        print(f"[SPLIT_LOG] Ошибка: {e}", flush=True)