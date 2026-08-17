# twinby_server.py — менеджер задач Twinby
import json, gzip
from datetime import datetime
import uuid
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shared import supabase, CANCEL_FLAGS, require_auth

app = FastAPI(title="CLAW-AI Twinby Manager")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class LikesTaskRequest(BaseModel):
    account_id: str
    limit: int = 10

class AutoReplyTaskRequest(BaseModel):
    account_id: str
    max_dialogs: int = 20

class StopTaskRequest(BaseModel):
    account_id: str

def enqueue_job(account_id: str, job_type: str, payload: dict) -> dict:
    existing = supabase.table("job_queue").select("id").eq("account_id", account_id).eq("type", job_type).in_("status", ["pending", "running"]).limit(1).execute()
    if existing.data:
        return existing.data[0]
    res = supabase.table("job_queue").insert({"account_id": account_id, "type": job_type, "payload": payload, "status": "pending"}).execute()
    return res.data[0]

@app.get("/")
def root():
    return {"ok": True, "service": "twinby-manager"}

@app.head("/")
def root_head():
    from fastapi.responses import Response
    return Response(status_code=200)

@app.head("/health")
def health_head():
    from fastapi.responses import Response
    return Response(status_code=200)

@app.get("/health")
def health():
    return {"ok": True, "service": "twinby-manager"}

@app.post("/api/tasks/twinby-likes")
def api_twinby_likes(payload: LikesTaskRequest):
    job = enqueue_job(payload.account_id, "likes-http", {"limit": payload.limit})
    return {"ok": True, "job_id": job["id"], "status": "pending"}

@app.post("/api/tasks/twinby-auto-reply")
def api_twinby_auto_reply(payload: AutoReplyTaskRequest):
    job = enqueue_job(payload.account_id, "auto-reply-http", {"max_dialogs": payload.max_dialogs})
    return {"ok": True, "job_id": job["id"], "status": "pending"}

@app.post("/api/tasks/stop")
def api_stop(payload: StopTaskRequest):
    CANCEL_FLAGS[payload.account_id] = True
    supabase.table("job_queue").update({"status": "cancelled"}).eq("account_id", payload.account_id).in_("status", ["pending", "running"]).execute()
    return {"ok": True}

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
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Dart/3.11 (dart:io)"}
    proxy_url = None
    if _px.get("use_proxy") and _px.get("host"):
        proxy_url = f"http://{_px['username']}:{_px['password']}@{_px['host']}:{_px['port']}"
    try:
        import httpx
        async with httpx.AsyncClient(proxy=proxy_url, timeout=45) as client:
            resp = await client.post("https://twinby.ru/api/auth/v2/auth/init", content=body, headers=headers)
        if resp.status_code not in (200, 202):
            raise HTTPException(status_code=400, detail=f"Twinby вернул {resp.status_code}")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/connect")
async def connect_twinby(payload: dict, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    
    email = (payload.get("twinby_email") or "").strip()
    code = (payload.get("twinby_code") or "").strip()
    account_name = (payload.get("account_name") or email).strip()
    
    if not email or not code:
        raise HTTPException(status_code=400, detail="Введи email и код из письма")
    
    import httpx, json as _json
    
    from proxy_loader import get_proxy as _gp2
    px = _gp2("twinby")
    proxy_url = None
    if px.get("use_proxy") and px.get("host"):
        proxy_url = f"http://{px['username']}:{px['password']}@{px['host']}:{px['port']}"
    
    body = _json.dumps({
        "login": email,
        "provider": "email", 
        "code": code,
    }, ensure_ascii=False).encode()
    
    async with httpx.AsyncClient(proxy=proxy_url, timeout=45) as client:
        resp = await client.post(
            "https://twinby.ru/api/auth/v2/auth/confirm",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Dart/3.11 (dart:io)",
            }
        )
    
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Неверный код или email (статус {resp.status_code})")
    
    data = resp.json()
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
        "id": account_id,
        "owner_email": require_auth(authorization)["email"],
        "platform": "Twinby",
        "name": account_name,
        "profile_url": "https://twinby.ru",
        "final_url": "https://twinby.ru",
        "title": account_name,
        "photo_url": photo_url,
        "cookies_count": 1,
        "cookies_valid": True,
        "session_valid": True,
        "session_reason": "JWT авторизация",
        "images_found": 0,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    
    supabase.table("accounts").insert(public_account).execute()
    supabase.table("accounts_private").insert({
        "id": account_id,
        "cookies_raw": token
    }).execute()
    
    return {
        "ok": True,
        "account": public_account,
        "warning": None if photo_url else "Фото не найдено — добавь вручную.",
    }

@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str):
    if not job_id or job_id == "undefined":
        return {"ok": False, "job": None}
    res = supabase.table("job_queue").select("*").eq("id", job_id).limit(1).execute()
    return {"ok": True, "job": res.data[0] if res.data else None}

@app.get("/api/jobs/account/{account_id}/active")
def api_get_active_job(account_id: str):
    res = supabase.table("job_queue").select("*").eq("account_id", account_id).in_("status", ["pending", "running"]).order("created_at", desc=True).limit(1).execute()
    return {"ok": True, "job": res.data[0] if res.data else None}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
