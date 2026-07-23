# mamba_server.py — микросервер для Mamba платформы
# Запуск: uvicorn mamba_server:app --host 0.0.0.0 --port 8002
import time
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared import (
    supabase, get_ai_settings, get_groq_keys, get_gemini_keys,
    build_system_prompt, call_groq_with_rotation, append_task_log,
    mark_account_blocked, telegram_was_sent, reserve_telegram_send,
    cancel_telegram_reservation, should_cancel, CANCEL_FLAGS, require_auth,
    push_split_log_sync,
)
from mamba_client import (
    parse_cookies,
    validate_cookies,
    task_auto_reply_http,
    task_likes_http,
    detect_account_status,
    get_profile_photo,
)

app = FastAPI(title="CLAW-AI Mamba Worker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ────────────────────────────────────────────────

class LikesTaskRequest(BaseModel):
    account_id: str
    limit: int = 10

class AutoReplyTaskRequest(BaseModel):
    account_id: str
    max_dialogs: int = 20

class StopTaskRequest(BaseModel):
    account_id: str

# ── Health ────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "service": "mamba"}

# ── Likes ─────────────────────────────────────────────────

@app.post("/api/tasks/likes-http")
def api_mamba_likes(payload: LikesTaskRequest):
    account_id = payload.account_id
    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Cookies не найдены")

    cookies = parse_cookies(res.data[0].get("cookies_raw", ""))
    result = task_likes_http(cookies, limit=payload.limit)

    if result.get("blocked"):
        mark_account_blocked(account_id)

    append_task_log({"account_id": account_id, "type": "likes", **result})
    return {"ok": True, **result}

# ── Auto Reply ────────────────────────────────────────────

@app.post("/api/tasks/auto-reply-http")
def api_mamba_auto_reply(payload: AutoReplyTaskRequest):
    account_id = payload.account_id
    settings = get_ai_settings(account_id)

    if not get_groq_keys(settings) and not get_gemini_keys(settings):
        raise HTTPException(status_code=400, detail="Не задан ни Groq, ни Gemini API ключ")

    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Cookies не найдены")

    cookies = parse_cookies(res.data[0].get("cookies_raw", ""))
    ok, missing = validate_cookies(cookies)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Не хватает кук: {', '.join(missing)}")

    settings["_account_id"] = account_id
    CANCEL_FLAGS[account_id] = False

    result = task_auto_reply_http(
        cookies=cookies,
        settings=settings,
        build_prompt_fn=build_system_prompt,
        call_groq_fn=call_groq_with_rotation,
        max_chats=payload.max_dialogs,
        should_cancel_fn=lambda: should_cancel(account_id),
        telegram_was_sent_fn=telegram_was_sent,
        reserve_telegram_send_fn=reserve_telegram_send,
        cancel_telegram_reservation_fn=cancel_telegram_reservation,
    )

    if result.get("blocked"):
        mark_account_blocked(account_id)

    append_task_log({"account_id": account_id, "type": "auto-reply-http", **result})
    return {"ok": True, **result}

# ── Auto Reply Loop ───────────────────────────────────────

@app.post("/api/tasks/auto-reply-http-loop")
def api_mamba_auto_reply_loop(payload: AutoReplyTaskRequest):
    account_id = payload.account_id
    settings = get_ai_settings(account_id)

    if not get_groq_keys(settings) and not get_gemini_keys(settings):
        raise HTTPException(status_code=400, detail="Не задан ни Groq, ни Gemini API ключ")

    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Cookies не найдены")

    cookies_raw = res.data[0].get("cookies_raw", "")
    cookies = parse_cookies(cookies_raw)
    ok, missing = validate_cookies(cookies)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Не хватает кук: {', '.join(missing)}")

    settings["_account_id"] = account_id
    CANCEL_FLAGS[account_id] = False

    total_replied = 0
    total_skipped = 0
    total_errors = 0
    total_contacts_sent = 0
    cycle = 0

    try:
        while not should_cancel(account_id):
            cycle += 1
            work_end = time.time() + 20 * 60
            print(f"[MAMBA LOOP] Цикл {cycle}", flush=True)

            supabase.table("accounts").update({
                "run_status": "running",
                "run_task": "auto-reply-loop",
                "run_note": f"Цикл {cycle}: работаю...",
            }).eq("id", account_id).execute()

            while time.time() < work_end and not should_cancel(account_id):
                result = task_auto_reply_http(
                    cookies=cookies,
                    settings=settings,
                    build_prompt_fn=build_system_prompt,
                    call_groq_fn=call_groq_with_rotation,
                    max_chats=payload.max_dialogs,
                    should_cancel_fn=lambda: should_cancel(account_id) or time.time() >= work_end,
                    telegram_was_sent_fn=telegram_was_sent,
                    reserve_telegram_send_fn=reserve_telegram_send,
                    cancel_telegram_reservation_fn=cancel_telegram_reservation,
                )

                if result.get("blocked"):
                    chain_result = mark_account_blocked(account_id)
                    return {
                        "ok": True,
                        "summary": f"Анкета заблокирована",
                        "cycles": cycle,
                        "replied": total_replied,
                        "reserve_account_id": chain_result.get("reserve_account_id"),
                    }

                total_replied += result.get("replied", 0)
                total_skipped += result.get("skipped", 0)
                total_errors += result.get("errors", 0)
                total_contacts_sent += result.get("contacts_sent", 0)
                append_task_log({"account_id": account_id, "type": "auto-reply-http", **result})

            if should_cancel(account_id):
                break

    finally:
        supabase.table("accounts").update({
            "run_status": "idle", "run_task": "", "run_note": "",
        }).eq("id", account_id).execute()

    return {
        "ok": True,
        "summary": f"Завершено циклов: {cycle}. Ответил {total_replied}, контактов {total_contacts_sent}.",
        "cycles": cycle,
        "replied": total_replied,
        "skipped": total_skipped,
        "errors": total_errors,
        "contacts_sent": total_contacts_sent,
    }

# ── Stop ──────────────────────────────────────────────────

@app.post("/api/tasks/stop")
def api_stop(payload: StopTaskRequest):
    CANCEL_FLAGS[payload.account_id] = True
    supabase.table("job_queue").update({"status": "cancelled"}).eq("account_id", payload.account_id).in_("status", ["pending", "running"]).execute()
    return {"ok": True}

# ── Debug ─────────────────────────────────────────────────

@app.get("/api/debug-rating")
def api_debug_rating(account_id: str):
    from mamba_client import get_rating
    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        return {"error": "cookies не найдены"}
    cookies = parse_cookies(res.data[0].get("cookies_raw", ""))
    return get_rating(cookies)

@app.get("/api/debug-chats-http")
def api_debug_chats_http(account_id: str):
    from mamba_client import get_chats
    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        return {"error": "cookies не найдены"}
    cookies = parse_cookies(res.data[0].get("cookies_raw", ""))
    return get_chats(cookies, limit=10)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)