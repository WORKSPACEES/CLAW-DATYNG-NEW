# vznakomstve_server.py — менеджер задач Vznakomstve
import json, gzip
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shared import supabase, CANCEL_FLAGS, require_auth

app = FastAPI(title="CLAW-AI Vznakomstve Manager")
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

@app.get("/health")
def health():
    return {"ok": True, "service": "vznakomstve-manager"}

@app.post("/api/tasks/vznakomstve-likes")
def api_vzn_likes(payload: LikesTaskRequest):
    job = enqueue_job(payload.account_id, "likes-http", {"limit": payload.limit})
    return {"ok": True, "job_id": job["id"], "status": "pending"}

@app.post("/api/tasks/vznakomstve-auto-reply")
def api_vzn_auto_reply(payload: AutoReplyTaskRequest):
    job = enqueue_job(payload.account_id, "auto-reply-http", {"max_dialogs": payload.max_dialogs})
    return {"ok": True, "job_id": job["id"], "status": "pending"}

@app.post("/api/tasks/stop")
def api_stop(payload: StopTaskRequest):
    CANCEL_FLAGS[payload.account_id] = True
    supabase.table("job_queue").update({"status": "cancelled"}).eq("account_id", payload.account_id).in_("status", ["pending", "running"]).execute()
    return {"ok": True}

@app.post("/api/vznakomstve/send-code")
async def vzn_send_code(payload: dict, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    email = (payload.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="email обязателен")
    import http.client as _hc
    boundary = "getx-http-boundary-CLAWAI"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"lang\"\r\n\r\nru\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"email\"\r\n\r\n{email}\r\n--{boundary}--\r\n").encode("utf-8")
    conn = _hc.HTTPSConnection("meet.wcase.net", timeout=15)
    conn.request("POST", "/email", body=body, headers={"Accept": "application/json", "Accept-Encoding": "gzip", "Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body)), "User-Agent": "InDating v3.2.6 (302060), Android 9, G011A", "Host": "meet.wcase.net"})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    if resp.getheader("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    if resp.status != 200:
        raise HTTPException(status_code=400, detail=f"Ошибка: {resp.status}")
    return {"ok": True}

@app.post("/api/vznakomstve/verify-code")
async def vzn_verify_code(payload: dict, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    email = (payload.get("email") or "").strip()
    code = (payload.get("code") or "").strip()
    if not email or not code:
        raise HTTPException(status_code=400, detail="email и code обязательны")
    import http.client as _hc
    boundary = "getx-http-boundary-CLAWAI"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"email\"\r\n\r\n{email}\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"code\"\r\n\r\n{code}\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"lang\"\r\n\r\nru\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"no_restore\"\r\n\r\n1\r\n--{boundary}--\r\n").encode("utf-8")
    conn = _hc.HTTPSConnection("meet.wcase.net", timeout=15)
    conn.request("POST", "/email", body=body, headers={"Accept": "application/json", "Accept-Encoding": "gzip", "Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body)), "User-Agent": "InDating v3.2.6 (302060), Android 9, G011A", "Host": "meet.wcase.net"})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    if resp.getheader("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8", errors="ignore"))
    token = data.get("data", {}).get("sid") or data.get("token") or ""
    if not token:
        raise HTTPException(status_code=400, detail=f"Неверный код: {str(data)[:200]}")
    body2 = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"token\"\r\n\r\n{token}\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"no_restore\"\r\n\r\n1\r\n--{boundary}--\r\n").encode("utf-8")
    conn2 = _hc.HTTPSConnection("meet.wcase.net", timeout=15)
    conn2.request("POST", "/login", body=body2, headers={"Accept": "application/json", "Accept-Encoding": "gzip", "Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body2)), "User-Agent": "InDating v3.2.6 (302060), Android 9, G011A", "Host": "meet.wcase.net"})
    resp2 = conn2.getresponse()
    raw2 = resp2.read()
    set_cookie = resp2.getheader("Set-Cookie") or ""
    conn2.close()
    if resp2.getheader("Content-Encoding") == "gzip":
        raw2 = gzip.decompress(raw2)
    phpsessid = ""
    for part in set_cookie.split(";"):
        if part.strip().startswith("PHPSESSID="):
            phpsessid = part.strip().split("=", 1)[1]
            break
    if not phpsessid:
        raise HTTPException(status_code=400, detail="Не удалось получить сессию")
    cookies_raw = json.dumps([{"name": "PHPSESSID", "value": phpsessid}])
    return {"ok": True, "cookies_raw": cookies_raw, "phpsessid": phpsessid}

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
    uvicorn.run(app, host="0.0.0.0", port=8005)
