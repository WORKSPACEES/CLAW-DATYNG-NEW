"""
Lovelaz — HTTP клиент без Playwright.
Работает через куки напрямую.
"""

import json
import re
import http.client
import gzip
import time
import socketio
from typing import Optional


BASE_HOST = "api.lovelaz.ru"
WEB_HOST = "lovelaz.online"
_build_id_cache: dict[str, tuple] = {}
_BUILD_ID_TTL = 300  # секунд
WS_ORIGIN = "https://lovelaz.ru"

def _proxy():
    return {"use_proxy": False}


def parse_cookies(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return {item["name"]: item["value"] for item in parsed if item.get("name")}
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    result = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            result[name.strip()] = value.strip()
    return result


def cookie_header(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _get_build_id(cookies: dict) -> Optional[str]:
    """Парсит buildId из __NEXT_DATA__ на главной странице. Кэш 5 минут."""
    import time as _time
    token = cookies.get("token", "")
    cache_key = token[:16] if token else "anon"

    if cache_key in _build_id_cache:
        cached_id, cached_at = _build_id_cache[cache_key]
        if _time.time() - cached_at < _BUILD_ID_TTL:
            return cached_id

    try:
        import base64
        conn = http.client.HTTPSConnection(WEB_HOST, timeout=45)
        conn.request("GET", "/", headers={
            "User-Agent": _proxy().get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
            "Cookie": cookie_header(cookies),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ru-RU,ru;q=0.9",
        })
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        html = raw.decode("utf-8", errors="ignore")
        match = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
        if match:
            build_id = match.group(1)
            _build_id_cache[cache_key] = (build_id, _time.time())
            print(f"[LOVELAZ] buildId получен: {build_id[:20]}...", flush=True)
            return build_id
    except Exception as e:
        print(f"[LOVELAZ] Не смог получить buildId: {e}", flush=True)
    return None


def _api_request(method: str, path: str, cookies: dict, body: dict = None) -> dict:
    """Запрос к api.lovelaz.ru."""
    token = cookies.get("token", "")
    headers = {
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Cookie": cookie_header(cookies),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
        "Origin": "https://lovelaz.ru",
        "Referer": "https://lovelaz.ru/",
    }
    body_bytes = None
    if body is not None:
        body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Length"] = str(len(body_bytes))

    try:
        import base64
        p = _proxy()
        if p.get("use_proxy") and p.get("host"):
            auth = base64.b64encode(f"{p['username']}:{p['password']}".encode()).decode()
            conn = http.client.HTTPSConnection(p["host"], p["port"], timeout=30)
            conn.set_tunnel(BASE_HOST, 443, {"Proxy-Authorization": f"Basic {auth}"})
        else:
            conn = http.client.HTTPSConnection(BASE_HOST, timeout=30)

        conn.request(method, path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()

        if resp.getheader("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)

        text = raw.decode("utf-8", errors="ignore")
        try:
            data = json.loads(text)
        except Exception:
            data = {"_raw": text}
        data["_status"] = resp.status
        return data
    except Exception as e:
        return {"_status": 0, "_error": str(e)}


def _next_request(path: str, cookies: dict) -> dict:
    """Запрос к lovelaz.ru (Next.js data endpoint)."""
    token = cookies.get("token", "")
    headers = {
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Authorization": f"Bearer {token}",
        "Cookie": cookie_header(cookies),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
        "Referer": "https://lovelaz.ru/",
    }
    try:
        import base64
        p = _proxy()
        if p.get("use_proxy") and p.get("host"):
            auth = base64.b64encode(f"{p['username']}:{p['password']}".encode()).decode()
            conn = http.client.HTTPSConnection(p["host"], p["port"], timeout=45)
            conn.set_tunnel(WEB_HOST, 443, {"Proxy-Authorization": f"Basic {auth}"})
        else:
            conn = http.client.HTTPSConnection(WEB_HOST, timeout=45)

        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()

        if resp.getheader("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)

        text = raw.decode("utf-8", errors="ignore")
        try:
            data = json.loads(text)
        except Exception:
            data = {"_raw": text}
        data["_status"] = resp.status
        return data
    except Exception as e:
        return {"_status": 0, "_error": str(e)}


def send_message(cookies: dict, chat_id: int, message: str, receiver_user_id: int) -> dict:
    """
    Отправляет сообщение через WebSocket (Socket.IO).
    """
    token = cookies.get("token", "")
    sio = socketio.SimpleClient()
    try:
        sio.connect(
            f"https://{BASE_HOST}",
            socketio_path="/socket.io",
            transports=["websocket"],
            headers={"Origin": WS_ORIGIN},
            auth={"token": token},
            wait_timeout=10,
        )
        sio.emit("message", {
            "chatId": chat_id,
            "message": message,
            "receiverUserId": receiver_user_id,
        })

        confirmed = False
        try:
            for _ in range(2):
                event = sio.receive(timeout=3)
                ev_name = event[0] if event else ""
                if ev_name == f"chat_{chat_id}":
                    confirmed = True
                    break
        except Exception:
            pass

        sio.disconnect()
        return {"_status": 200 if confirmed else 202, "confirmed": confirmed}
    except Exception as e:
        try:
            sio.disconnect()
        except Exception:
            pass
        return {"_status": 0, "_error": str(e)}


# ── API методы ────────────────────────────────────────────

def get_profiles_for_likes(cookies: dict, limit: int = 20) -> list[dict]:
    all_profiles = []
    seen_ids = set()
    max_attempts = 20

    for attempt in range(max_attempts):
        if len(all_profiles) >= limit:
            break

        resp = _api_request("POST", "/likes/dating", cookies, body={})
        profiles = resp.get("profiles") or []

        if not profiles:
            print(f"[LOVELAZ] Попытка {attempt+1}: анкеты закончились", flush=True)
            break

        new_count = 0
        for p in profiles:
            pid = p.get("id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_profiles.append(p)
                new_count += 1

        print(f"[LOVELAZ] Попытка {attempt+1}: получено {len(profiles)}, новых {new_count}, всего {len(all_profiles)}/{limit}", flush=True)

        if new_count == 0:
            print(f"[LOVELAZ] Все анкеты уже видели — стоп", flush=True)
            break

        pass

    print(f"[LOVELAZ] Итого анкет для лайков: {len(all_profiles)}", flush=True)
    return all_profiles[:limit]


def like_profile(cookies: dict, profile_id: int) -> dict:
    """Поставить лайк. POST /likes"""
    resp = _api_request("POST", "/likes", cookies, body={"like": True, "profileId": profile_id})
    print(f"[LOVELAZ] Лайк {profile_id}: статус={resp.get('_status')}", flush=True)
    return resp


def get_chats(cookies: dict) -> dict:
    """Получить список чатов через Next.js."""
    build_id = _get_build_id(cookies)
    if not build_id:
        return {"_status": 0, "_error": "Не смог получить buildId"}
    path = f"/_next/data/{build_id}/chat.json"
    resp = _next_request(path, cookies)
    count = (
        resp.get("pageProps", {})
        .get("chats", {})
        .get("pagination", {})
        .get("count", 0)
    )
    print(f"[LOVELAZ] Чатов найдено: {count}", flush=True)
    return resp


def get_chat_messages(cookies: dict, chat_id: int) -> dict:
    """Получить историю конкретного чата. GET /_next/data/{buildId}/chat/{chat_id}.json"""
    build_id = _get_build_id(cookies)
    if not build_id:
        return {"_status": 0, "_error": "Не смог получить buildId"}
    path = f"/_next/data/{build_id}/chat/{chat_id}.json"
    return _next_request(path, cookies)


def check_session(cookies: dict) -> dict:
    """Проверяет валидность сессии — пробует получить анкеты для лайков."""
    resp = _api_request("POST", "/likes/dating", cookies, body={})
    return resp


def detect_account_status(cookies: dict) -> dict:
    """Возвращает status: valid / logged_out / unknown."""
    try:
        resp = check_session(cookies)
        print(f"[LOVELAZ DETECT_STATUS] status={resp.get('_status')} body={json.dumps(resp, ensure_ascii=False, default=str)[:400]}", flush=True)
    except Exception as e:
        return {"status": "unknown", "reason": str(e), "http_status": 0}

    status = resp.get("_status", 0)

    if 200 <= status < 300:
        return {"status": "valid", "reason": "Анкета активна", "http_status": status}

    if status == 401:
        return {"status": "logged_out", "reason": "Cookies недействительны", "http_status": status}

    # Голый 403 — может быть рейт-лимит/антибот, а не реальный разлогин.
    if status == 403:
        return {"status": "unknown", "reason": "HTTP 403 без явного маркера разлогина (временная ошибка?)", "http_status": status}

    return {"status": "unknown", "reason": f"HTTP {status}", "http_status": status}

def get_profile_photo(cookies: dict) -> Optional[str]:
    """Ищет фото через разные эндпоинты."""
    endpoints = [
        ("GET", "/profile"),
        ("GET", "/profile/me"),
        ("GET", "/user"),
        ("GET", "/users/me"),
        ("GET", "/account"),
        ("GET", "/account/me"),
        ("GET", "/auth/me"),
    ]
    for method, path in endpoints:
        resp = _api_request(method, path, cookies)
        status = resp.get("_status")
        print(f"[LOVELAZ PHOTO] {path} status={status}", flush=True)
        if status in (200, 201):
            print(f"[LOVELAZ PHOTO] resp={json.dumps(resp, ensure_ascii=False, default=str)[:300]}", flush=True)
            avatar = resp.get("avatar") or {}
            image = avatar.get("image", "")
            if image:
                url = f"https://api.lovelaz.online{image}" if image.startswith("/") else image
                return url
    return None


# ── Высокоуровневые задачи ────────────────────────────────

def task_likes_http(cookies: dict, limit: int = 20) -> dict:
    """Ставит лайки через HTTP."""
    liked = 0
    skipped = 0
    errors = 0

    profiles = get_profiles_for_likes(cookies, limit=limit)

    for profile in profiles:
        profile_id = profile.get("id")
        name = profile.get("name", str(profile_id))

        if not profile_id:
            skipped += 1
            continue

        try:
            result = like_profile(cookies, profile_id)
            if result.get("_status") in (200, 201):
                liked += 1
                print(f"[LOVELAZ LIKES] ✓ {name} ({profile_id})", flush=True)
            else:
                print(f"[LOVELAZ LIKES] ✗ {name}: {result}", flush=True)
                errors += 1
        except Exception as e:
            print(f"[LOVELAZ LIKES] ✗ {name}: {e}", flush=True)
            errors += 1

    return {"liked": liked, "skipped": skipped, "errors": errors}


def task_get_all_chats_with_history(cookies: dict, max_chats: int = 30) -> list[dict]:
    build_id = _get_build_id(cookies)
    print(f"[LOVELAZ DEBUG] build_id={build_id}", flush=True)
    if not build_id:
        print("[LOVELAZ] Не смог получить buildId — чаты недоступны", flush=True)
        return []

    chats_resp = _next_request(f"/_next/data/{build_id}/chat.json", cookies)
    print(f"[LOVELAZ DEBUG] chats_resp status={chats_resp.get('_status')} keys={list(chats_resp.keys())}", flush=True)
    print(f"[LOVELAZ DEBUG] chats_resp raw (first 500): {json.dumps(chats_resp, ensure_ascii=False, default=str)[:500]}", flush=True)

    chats_raw = (
        chats_resp.get("pageProps", {})
        .get("chats", {})
        .get("data", [])
    )

    print(f"[LOVELAZ] Чатов: {len(chats_raw)}", flush=True)

    result = []

    for chat in chats_raw[:max_chats]:
        chat_id = chat.get("id")
        if not chat_id:
            continue

        msgs_resp = get_chat_messages(cookies, chat_id)
        messages_obj = msgs_resp.get("pageProps", {}).get("messages", {})
        msgs_raw = messages_obj.get("data", [])
        if not msgs_raw:
            print(f"[LOVELAZ DEBUG] chat {chat_id}: статус={msgs_resp.get('_status')}, "
                  f"keys={list(msgs_resp.keys())[:5]}", flush=True)
        target = messages_obj.get("target_profile", {})
        name = target.get("name") or str(chat_id)
        blocked = target.get("blocked", False)

        my_profile_id = msgs_resp.get("profile", {}).get("id")
        receiver_user_id = target.get("userId") or target.get("id")

        if blocked:
            continue

        history = []
        for msg in msgs_raw:
            text = (msg.get("message") or "").strip()
            if not text:
                continue
            is_incoming = msg.get("profile_id") != my_profile_id
            history.append({
                "role": "user" if is_incoming else "assistant",
                "content": text,
            })

        if not history:
            continue

        result.append({
            "chat_id": chat_id,
            "name": name,
            "history": history,
            "last_role": history[-1]["role"],
            "receiver_user_id": receiver_user_id,
        })

    return result


def task_auto_reply_http(
    cookies: dict,
    settings: dict,
    build_prompt_fn,
    call_groq_fn,
    max_chats: int = 5,
    should_cancel_fn=None,
) -> dict:
    """Авто-ответ для Lovelaz — аналог mamba_client.task_auto_reply_http."""

    status_check = detect_account_status(cookies)
    if status_check["status"] == "logged_out":
        return {"replied": 0, "skipped": 0, "errors": 0, "contacts_sent": 0,
                "blocked": False, "logged_out": True}

    account_id = settings.get("_account_id", "")
    system_prompt = build_prompt_fn(settings)
    contacts = (settings.get("contacts") or "").strip()

    replied = 0
    skipped = 0
    errors = 0
    contacts_sent = 0

    chats = task_get_all_chats_with_history(cookies, max_chats=max_chats)
    # Берём только чаты где последнее сообщение от собеседника
    chats = [c for c in chats if c.get("last_role") == "user"]

    for chat in chats:
        if should_cancel_fn and should_cancel_fn():
            print("[LOVELAZ AUTO-REPLY] Отмена", flush=True)
            break

        chat_id = chat["chat_id"]
        history = chat["history"]
        name = chat["name"]

        if not history or history[-1]["role"] != "user":
            skipped += 1
            continue

        # продолжаем отвечать даже если контакт уже отправлен

        print(f"[LOVELAZ AUTO-REPLY] {name} (chat {chat_id}): генерирую...", flush=True)

        try:
            reply = call_groq_fn(
                account_id=account_id,
                settings=settings,
                system_prompt=system_prompt,
                messages=history[-20:],
            )
        except Exception as e:
            print(f"[LOVELAZ AUTO-REPLY] Groq ошибка: {e}", flush=True)
            errors += 1
            continue

        if not reply:
            skipped += 1
            continue

        if should_cancel_fn and should_cancel_fn():
            break

        receiver_user_id = chat.get("receiver_user_id")
        if not receiver_user_id:
            print(f"[LOVELAZ AUTO-REPLY] {name}: нет receiver_user_id, пропускаю", flush=True)
            skipped += 1
            continue

        try:
            if contacts and contacts.lower() in reply.lower():
                reply_without_contact = reply.replace(contacts, "").strip().strip("—-,. ")
                if reply_without_contact:
                    send_message(cookies, chat_id, reply_without_contact, receiver_user_id)
                send_result = send_message(cookies, chat_id, contacts, receiver_user_id)
                status = send_result.get("_status")
                if status in (200, 202):
                    replied += 1
                    contacts_sent += 1
                    print(f"[LOVELAZ AUTO-REPLY] {name}: ✓ контакт отправлен отдельно", flush=True)
                else:
                    errors += 1
                    print(f"[LOVELAZ AUTO-REPLY] {name}: ✗ ошибка отправки контакта: {send_result}", flush=True)
            else:
                send_result = send_message(cookies, chat_id, reply, receiver_user_id)
                status = send_result.get("_status")
                if status in (200, 202):
                    replied += 1
                    print(f"[LOVELAZ AUTO-REPLY] {name}: ✓ ответ отправлен", flush=True)
                else:
                    errors += 1
                    print(f"[LOVELAZ AUTO-REPLY] {name}: ✗ ошибка отправки: {send_result}", flush=True)
        except Exception as e:
            errors += 1
            print(f"[LOVELAZ AUTO-REPLY] {name}: ✗ исключение при отправке: {e}", flush=True)
            continue

        pass

    return {
        "replied": replied,
        "skipped": skipped,
        "errors": errors,
        "contacts_sent": contacts_sent,
    }
