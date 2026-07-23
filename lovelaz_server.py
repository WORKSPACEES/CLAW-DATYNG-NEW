# lovelaz_server.py — микросервер для Lovelaz платформы
# Запуск: uvicorn lovelaz_server:app --host 0.0.0.0 --port 8003
import time
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared import (
    supabase, get_ai_settings, get_groq_keys, get_gemini_keys,
    build_system_prompt, call_groq_with_rotation, append_task_log,
    mark_account_blocked, should_cancel, CANCEL_FLAGS, require_auth,
)
from lovelaz_client import (
    parse_cookies,
    detect_account_status,
    task_likes_http,
    task_auto_reply_http,
    get_profile_photo,
)

app = FastAPI(title="CLAW-AI Lovelaz Worker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LikesTaskRequest(BaseModel):
    account_id: str
    limit: int = 10

class AutoReplyTaskRequest(BaseModel):
    account_id: str
    max_dialogs: int = 20

class StopTaskRequest(BaseModel):
    account_id: str

@app.get("/health")
def health():
    return {"ok": True, "service": "lovelaz"}

@app.post("/api/tasks/lovelaz-likes")
def api_lovelaz_likes(payload: LikesTaskRequest):
    account_id = payload.account_id
    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Cookies не найдены")

    cookies = parse_cookies(res.data[0].get("cookies_raw", ""))
    result = task_likes_http(cookies, limit=payload.limit)

    if result.get("blocked") or result.get("status") == "profile_blocked":
        mark_account_blocked(account_id)
        result["blocked"] = True

    append_task_log({"account_id": account_id, "type": "likes", **result})
    return {"ok": True, **result}

@app.post("/api/tasks/lovelaz-auto-reply")
def api_lovelaz_auto_reply(payload: AutoReplyTaskRequest):
    account_id = payload.account_id
    settings = get_ai_settings(account_id)

    if not get_groq_keys(settings) and not get_gemini_keys(settings):
        raise HTTPException(status_code=400, detail="Не задан ни Groq, ни Gemini API ключ")

    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Cookies не найдены")

    cookies = parse_cookies(res.data[0].get("cookies_raw", ""))
    settings["_account_id"] = account_id
    CANCEL_FLAGS[account_id] = False

    result = task_auto_reply_http(
        cookies=cookies,
        settings=settings,
        build_prompt_fn=build_system_prompt,
        call_groq_fn=call_groq_with_rotation,
        max_chats=payload.max_dialogs,
        should_cancel_fn=lambda: should_cancel(account_id),
    )

    if result.get("blocked"):
        mark_account_blocked(account_id)

    append_task_log({"account_id": account_id, "type": "auto-reply-http", **result})
    return {"ok": True, **result}

@app.post("/api/tasks/stop")
def api_stop(payload: StopTaskRequest):
    CANCEL_FLAGS[payload.account_id] = True
    supabase.table("job_queue").update({"status": "cancelled"}).eq("account_id", payload.account_id).in_("status", ["pending", "running"]).execute()
    return {"ok": True}

@app.get("/api/debug-lovelaz-chats")
def api_debug_lovelaz_chats(account_id: str):
    from lovelaz_client import task_get_all_chats_with_history
    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        return {"error": "cookies не найдены"}
    cookies = parse_cookies(res.data[0].get("cookies_raw", ""))
    chats = task_get_all_chats_with_history(cookies, max_chats=5)
    return {"ok": True, "chats_count": len(chats), "chats": chats}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)