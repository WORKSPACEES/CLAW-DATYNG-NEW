# twinby_server.py — микросервер для Twinby платформы
# Запуск: uvicorn twinby_server:app --host 0.0.0.0 --port 8004
import time
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared import (
    supabase, get_ai_settings, get_groq_keys, get_gemini_keys,
    build_system_prompt, call_groq_with_rotation, append_task_log,
    mark_account_blocked, should_cancel, CANCEL_FLAGS, require_auth,
)
from twinby_client import (
    parse_cookies,
    extract_jwt,
    detect_account_status,
    task_likes_http,
    task_auto_reply_http,
    get_me,
)

app = FastAPI(title="CLAW-AI Twinby Worker")

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

class SendCodeRequest(BaseModel):
    email: str

class ConnectRequest(BaseModel):
    account_name: str
    twinby_email: str
    twinby_code: str

@app.get("/health")
def health():
    return {"ok": True, "service": "twinby"}

@app.post("/api/twinby/send-code")
async def twinby_send_code(payload: dict, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    email = (payload.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="email обязателен")

    from proxy_loader import get_proxy as _gp
    import json as _json
    _px = _gp("twinby")

    body = _json.dumps({"login": email, "provider": "email", "codeSender": "email"}, ensure_ascii=False)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Dart/3.11 (dart:io)",
    }

    proxy_url = None
    if _px.get("use_proxy") and _px.get("host"):
        proxy_url = f"socks5h://{_px['username']}:{_px['password']}@{_px['host']}:{_px['port']}"

    try:
        import httpx
        async with httpx.AsyncClient(proxy=proxy_url, timeout=15) as client:
            resp = await client.post("https://twinby.ru/api/auth/v2/auth/init", content=body, headers=headers)
        if resp.status_code not in (200, 202):
            raise HTTPException(status_code=400, detail=f"Twinby вернул {resp.status_code}")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[TWINBY SEND-CODE ERROR] {e}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/twinby-likes")
def api_twinby_likes(payload: LikesTaskRequest):
    account_id = payload.account_id
    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Cookies не найдены")

    token = extract_jwt(res.data[0].get("cookies_raw", ""))
    result = task_likes_http(token, limit=payload.limit)

    if result.get("blocked"):
        mark_account_blocked(account_id)

    append_task_log({"account_id": account_id, "type": "likes", **result})
    return {"ok": True, **result}

@app.post("/api/tasks/twinby-auto-reply")
def api_twinby_auto_reply(payload: AutoReplyTaskRequest):
    account_id = payload.account_id
    settings = get_ai_settings(account_id)

    if not get_groq_keys(settings) and not get_gemini_keys(settings):
        raise HTTPException(status_code=400, detail="Не задан ни Groq, ни Gemini API ключ")

    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Cookies не найдены")

    token = extract_jwt(res.data[0].get("cookies_raw", ""))
    settings["_account_id"] = account_id
    CANCEL_FLAGS[account_id] = False

    result = task_auto_reply_http(
        token=token,
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

@app.get("/api/debug/twinby-me/{account_id}")
def debug_twinby_me(account_id: str):
    res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
    if not res.data:
        return {"error": "not found"}
    token = extract_jwt(res.data[0].get("cookies_raw", ""))
    return {"raw": get_me(token)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)