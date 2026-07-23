# vznakomstve_server.py — микросервер для Vznakomstve платформы
# Запуск: uvicorn vznakomstve_server:app --host 0.0.0.0 --port 8005
import json
import gzip
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared import (
    supabase, get_ai_settings, get_groq_keys, get_gemini_keys,
    build_system_prompt, call_groq_with_rotation, append_task_log,
    mark_account_blocked, should_cancel, CANCEL_FLAGS, require_auth,
)
from vznakomstve_client import (
    parse_cookies,
    detect_account_status,
    task_likes_http,
    task_auto_reply_http,
    get_profile_photo,
)

app = FastAPI(title="CLAW-AI Vznakomstve Worker")

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
    return {"ok": True, "service": "vznakomstve"}

@app.post("/api/vznakomstve/send-code")
async def vzn_send_code(payload: dict, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    email = (payload.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="email обязателен")

    import http.client as _hc
    conn = _hc.HTTPSConnection("meet.wcase.net", timeout=15)
    boundary = "getx-http-boundary-CLAWAI"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="lang"\r\n\r\nru\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="email"\r\n\r\n{email}\r\n'
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    conn.request("POST", "/email", body=body, headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
        "User-Agent": "InDating v3.2.6 (302060), Android 9, G011A",
        "Host": "meet.wcase.net",
    })
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    if resp.getheader("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8", errors="ignore")
    if resp.status != 200:
        raise HTTPException(status_code=400, detail=f"Ошибка отправки кода: {resp.status}")
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

    conn = _hc.HTTPSConnection("meet.wcase.net", timeout=15)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="email"\r\n\r\n{email}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="code"\r\n\r\n{code}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="lang"\r\n\r\nru\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="no_restore"\r\n\r\n1\r\n'
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    conn.request("POST", "/email", body=body, headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
        "User-Agent": "InDating v3.2.6 (302060), Android 9, G011A",
        "Host": "meet.wcase.net",
    })
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    if resp.getheader("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8", errors="ignore"))
    token = data.get("data", {}).get("sid") or data.get("token") or data.get("sid") or ""
    if not token:
        raise HTTPException(status_code=400, detail=f"Неверный код. Ответ: {str(data)[:200]}")

    conn2 = _hc.HTTPSConnection("meet.wcase.net", timeout=15)
    body2 = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="token"\r\n\r\n{token}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="no_restore"\r\n\r\n1\r\n'
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    conn2.request("POST", "/login", body=body2, headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body2)),
        "User-Agent": "InDating v3.2.6 (302060), Android 9, G011A",
        "Host": "meet.wcase.net",
    })
    resp2 = conn2.getresponse()
    raw2 = resp2.read()
    set_cookie = resp2.getheader("Set-Cookie") or ""
    conn2.close()
    if resp2.getheader("Content-Encoding") == "gzip":
        raw2 = gzip.decompress(raw2)

    phpsessid = ""
    for part in set_cookie.split(";"):
        part = part.strip()
        if part.startswith("PHPSESSID="):
            phpsessid = part.split("=", 1)[1]
            break

    if not phpsessid:
        data2 = json.loads(raw2.decode("utf-8", errors="ignore"))
        phpsessid = data2.get("data", {}).get("sid") or ""

    if not phpsessid:
        raise HTTPException(status_code=400, detail="Не удалось получить сессию")

    cookies_raw = json.dumps([{"name": "PHPSESSID", "value": phpsessid}])
    return {"ok": True, "cookies_raw": cookies_raw, "phpsessid": phpsessid}

@app.post("/api/tasks/vznakomstve-likes")
def api_vzn_likes(payload: LikesTaskRequest):
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

@app.post("/api/tasks/vznakomstve-auto-reply")
def api_vzn_auto_reply(payload: AutoReplyTaskRequest):
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)