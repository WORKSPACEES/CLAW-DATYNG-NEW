"""
Vznakomstve — HTTP клиент.
Работает через meet.wcase.net (мобильное API).
"""

import json
import re
import time
import urllib.parse
import http.client
import gzip
import base64
from typing import Optional


BASE_HOST = "meet.wcase.net"
API_BASE = "/api"

from proxy_loader import get_proxy as _get_proxy
def _proxy():
    return _get_proxy("vznakomstve")


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
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if k == "PHPSESSID")


def _ts() -> int:
    return int(time.time() * 1000)


def _api_request(method: str, path: str, cookies: dict, body: dict = None, form: dict = None) -> dict:
    x_token = cookies.get("x_token", "")
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "Content-Type": "application/json; charset=utf-8",
        "Connection": "keep-alive",
        "Cookie": cookie_header(cookies),
        "User-Agent": _proxy().get("user_agent") or "InDating v3.2.6 (302060), Android 9, A5010, A5010, msm8998, PI",
        "Host": "meet.wcase.net",
    }
    if x_token:
        headers["x-token"] = x_token

    body_bytes = None
    if form is not None:
        # multipart/form-data как в реальном приложении
        boundary = "getx-http-boundary-vzn"
        parts = []
        for key, value in form.items():
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
            )
        body_str = "".join(parts) + f"--{boundary}--\r\n"
        body_bytes = body_str.encode("utf-8")
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        headers["Content-Length"] = str(len(body_bytes))
    elif body is not None:
        body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Length"] = str(len(body_bytes))

    try:
        p = _proxy()
        if p.get("use_proxy") and p.get("host"):
            auth = base64.b64encode(f"{p['username']}:{p['password']}".encode()).decode()
            conn = http.client.HTTPSConnection(p["host"], p["port"], timeout=30)
            conn.set_tunnel(BASE_HOST, 443, {
                "Proxy-Authorization": f"Basic {auth}"
            })
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
        if isinstance(data, list):
            data = {"_list": data}
        data["_status"] = resp.status
        return data
    except Exception as e:
        return {"_status": 0, "_error": str(e)}


# ── API методы ────────────────────────────────────────────

def get_my_id(cookies: dict) -> Optional[str]:
    resp = _api_request("GET", f"{API_BASE}/get-users", cookies)
    print(f"[VZN get_my_id] status={resp.get('_status')} keys={list(resp.keys())[:10]}", flush=True)
    if resp.get("_status") == 200:
        items = resp.get("items") or resp.get("_list") or []
        if items:
            uid = items[0].get("id") or items[0].get("user_id") or items[0].get("owner_id")
            if uid:
                print(f"[VZN get_my_id] найден: {uid}", flush=True)
                return str(uid)
        item = resp.get("item") or {}
        uid = item.get("id") or item.get("user_id")
        if uid:
            return str(uid)
    print(f"[VZN get_my_id] raw={str(resp)[:300]}", flush=True)
    return None


def detect_account_status(cookies: dict) -> dict:
    resp = _api_request("GET", f"{API_BASE}/get-contacts-offset?offset=0", cookies)
    status = resp.get("_status", 0)
    if status == 200:
        return {"status": "valid", "http_status": status}
    if status == 401:
        return {"status": "logged_out", "reason": "Сессия истекла", "http_status": status}
    if status == 403:
        return {"status": "blocked", "reason": "Доступ запрещён", "http_status": status}
    return {"status": "unknown", "reason": f"HTTP {status}", "http_status": status}


def get_likes(cookies: dict, offset: int = 0, s: str = "") -> dict:
    """Получить входящие лайки."""
    path = f"{API_BASE}/get-likes?offset={offset}"
    return _api_request("GET", path, cookies)


def set_like(cookies: dict, user_id: str) -> dict:
    """Поставить лайк пользователю."""
    path = f"{API_BASE}/set-like?user_id={user_id}"
    return _api_request("GET", path, cookies)


def get_contacts(cookies: dict, offset: int = 0) -> dict:
    """Получить список чатов."""
    path = f"{API_BASE}/get-contacts-offset?offset={offset}"
    return _api_request("GET", path, cookies)


def get_chat_history(cookies: dict, user_id: str) -> dict:
    path = f"{API_BASE}/get-messages-offset?user_id={user_id}&offset=0"
    resp = _api_request("GET", path, cookies)
    # get-messages-offset возвращает список напрямую в _list
    if "_list" in resp:
        resp["messagesItems"] = resp["_list"]
    return resp

def get_user_city(cookies: dict, user_id: str) -> str:
    """Получить город пользователя."""
    resp = _api_request("GET", f"{API_BASE}/get-user?id={user_id}", cookies)
    if resp.get("_status") == 200:
        item = resp.get("item") or {}
        return str(item.get("city") or "").lower().strip()
    return ""

def send_message(cookies: dict, user_id: str, message: str) -> dict:
    """Отправить сообщение пользователю."""
    path = f"{API_BASE}/add-message"
    form = {
        "user_id": user_id,
        "message": message,
        "captcha": "1",
    }
    return _api_request("POST", path, cookies, form=form)


def set_readed(cookies: dict, user_id: str) -> dict:
    """Пометить сообщения как прочитанные."""
    path = f"{API_BASE}/set-readed?user_id={user_id}"
    return _api_request("GET", path, cookies)


def get_profile_photo(cookies: dict) -> Optional[str]:
    """Возвращает URL фото профиля."""
    resp = _api_request("GET", f"{API_BASE}/get-users", cookies)
    print(f"[VZN PHOTO] status={resp.get('_status')}", flush=True)
    if resp.get("_status") != 200:
        return None
    items = resp.get("items") or []
    if items:
        url = (items[0].get("avatar_big") or items[0].get("avatar_small") or "").strip()
        print(f"[VZN PHOTO] avatar={url}", flush=True)
        return url or None
    item = resp.get("item") or {}
    url = (item.get("avatar_big") or item.get("avatar_small") or "").strip()
    print(f"[VZN PHOTO] item avatar={url}", flush=True)
    return url or None

def download_profile_photo(cookies: dict) -> Optional[str]:
    """Скачивает фото профиля через токен и возвращает локальный путь."""
    import os, uuid
    
    url = get_profile_photo(cookies)
    if not url:
        return None
    
    x_token = cookies.get("x_token", "")
    headers = {
        "User-Agent": "InDating v3.2.6 (302060), Android 9, A5010, A5010, msm8998, PI",
        "x-token": x_token,
        "Host": "vk-meet-app.s3-eu-west-1.amazonaws.com",
    }
    
    try:
        import http.client, ssl
        parsed = urllib.parse.urlparse(url)
        conn = http.client.HTTPSConnection(parsed.netloc, timeout=15)
        conn.request("GET", parsed.path, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        
        if resp.status == 200:
            save_dir = "/home/ubuntu/CLAW-DATYNG/static/photos"
            os.makedirs(save_dir, exist_ok=True)
            filename = f"vzn_{uuid.uuid4().hex}.jpg"
            filepath = os.path.join(save_dir, filename)
            with open(filepath, "wb") as f:
                f.write(raw)
            return f"/static/photos/{filename}"
    except Exception as e:
        print(f"[VZN PHOTO DOWNLOAD] ошибка: {e}", flush=True)
    
    return url  # fallback — оригинальный URL


# ── Высокоуровневые задачи ────────────────────────────────

def task_likes_http(cookies: dict, limit: int = 20, log_fn=None) -> dict:
    """Ставит лайки входящим симпатиям."""

    def _log(msg):
        print(f"[VZNAKOMSTVE LIKES] {msg}", flush=True)
        if log_fn:
            try:
                log_fn(msg)
            except Exception:
                pass

    liked = 0
    skipped = 0
    errors = 0

    likes_resp = get_likes(cookies, offset=0)
    if likes_resp.get("_status") != 200:
        _log(f"Ошибка получения лайков: статус={likes_resp.get('_status')}")
        return {"liked": liked, "skipped": skipped, "errors": errors}

    items = likes_resp.get("items") or []
    _log(f"Входящих лайков: {len(items)}")

    seen = set()
    for item in items[:limit]:
        user_id = str(item.get("owner_id") or item.get("user_id") or "")
        if not user_id or user_id in seen:
            skipped += 1
            continue
        seen.add(user_id)

        try:
            result = set_like(cookies, user_id)
            status = result.get("_status")
            if status == 200:
                liked += 1
                _log(f"✓ Лайк поставлен: {user_id}")
            else:
                _log(f"✗ {user_id}: статус={status}")
                errors += 1
        except Exception as e:
            _log(f"✗ {user_id}: ошибка {e}")
            errors += 1

    return {"liked": liked, "skipped": skipped, "errors": errors}


def task_get_all_chats_with_history(cookies: dict, max_chats: int = 30, my_global_id: str = "") -> list[dict]:
    """Получает все чаты с историей переписки."""
    result = []
    print(f"[VZN] my_global_id={my_global_id}", flush=True)

    chats_resp = get_contacts(cookies, offset=0)
    if chats_resp.get("_status") != 200:
        print(f"[VZNAKOMSTVE] Ошибка получения чатов: {chats_resp.get('_status')}", flush=True)
        return result

    contacts = chats_resp.get("contactsItems") or []
    print(f"[VZNAKOMSTVE] Чатов: {len(contacts)}", flush=True)

    for contact in contacts[:max_chats]:
        user_id = str(contact.get("user_id") or "")
        if not user_id:
            continue

        unread = int(contact.get("unread_count") or 0)
        city = get_user_city(cookies, user_id)
        name = user_id  # временно, до получения истории
        print(f"[VZN CONTACT] {user_id}: city='{city}'", flush=True)

        allowed_cities = ["москва", "moscow", "санкт-петербург", "питер", "saint-petersburg", "спб", "петербург"]
        if city and not any(c in city for c in allowed_cities):
            print(f"[VZN FILTER] Пропускаю {name} — город: '{city}'", flush=True)
            continue

        history_resp = get_chat_history(cookies, user_id)
        users_map = history_resp.get("messagesUsersItems") or {}
        if isinstance(users_map, dict) and len(users_map) >= 2:
            # Берём тот ключ который НЕ равен user_id собеседника
            for k in users_map.keys():
                if str(k) != str(user_id):
                    my_id = str(k)
                    break
            else:
                my_id = my_global_id
        else:
            my_id = my_global_id
        msgs_raw = history_resp.get("messagesItems") or []

        print(f"[VZN DEBUG] my_id={my_id} user_id={user_id} msgs_raw_type={type(msgs_raw).__name__} keys={list(history_resp.keys())[:5]}", flush=True)

        if isinstance(msgs_raw, dict):
            all_msgs = []
            for uid, msgs in msgs_raw.items():
                if isinstance(msgs, list):
                    all_msgs.extend(msgs)
            all_msgs.sort(key=lambda m: m.get("datetime") or "")
        elif isinstance(msgs_raw, list):
            all_msgs = sorted(msgs_raw, key=lambda m: m.get("datetime") or "")
        else:
            all_msgs = []

        history = []
        print(f"[VZN ROLES] my_id={my_id} user_id={user_id}", flush=True)
        for m in all_msgs[-5:]:
            sid = str(m.get("owner_id") or m.get("sender_id") or "")
            print(f"  sender={sid} is_mine={sid==my_id} text={m.get('message','')[:30]}", flush=True)
        for msg in all_msgs[-20:]:
            text = (msg.get("message") or msg.get("text") or "").strip()
            text = re.sub(r":[a-zA-Z0-9_+\-]+:", "", text).strip()
            text = re.sub(r"<[^>]+>", "", text).strip()
            if not text:
                continue
            if "сообщение не поддерживается" in text.lower():
                continue
            sender_id = str(msg.get("owner_id") or msg.get("sender_id") or "")
            print(f"[VZN MSG] owner_id={sender_id} my_id={my_id} text={text[:20]}", flush=True)
            is_incoming = (sender_id != my_id) if my_id else True
            history.append({
                "role": "user" if is_incoming else "assistant",
                "content": text,
            })

        if not history:
            continue

        print(f"[VZN DEBUG] {name} ({city}): {len(history)} сообщ, последнее: [{history[-1]['role']}] {history[-1]['content'][:40]}", flush=True)

        result.append({
            "user_id": user_id,
            "name": name,
            "history": history,
            "last_role": history[-1]["role"],
            "unread": unread,
        })

    return result


def task_auto_reply_http(
    cookies: dict,
    settings: dict,
    build_prompt_fn,
    call_groq_fn,
    max_chats: int = 30,
    should_cancel_fn=None,
    log_fn=None,
) -> dict:
    """Авто-ответ для Vznakomstve."""

    account_id = settings.get("_account_id", "")
    system_prompt = build_prompt_fn(settings)
    contacts = (settings.get("contacts") or "").strip()

    replied = 0
    skipped = 0
    errors = 0
    contacts_sent = 0

    def _log(msg):
        print(f"[VZNAKOMSTVE AUTO-REPLY] {msg}", flush=True)
        if log_fn:
            try:
                log_fn(msg)
            except Exception:
                pass

    my_global_id = get_my_id(cookies) or ""
    print(f"[VZN MY_ID] Глобальный my_id: '{my_global_id}'", flush=True)
    if not my_global_id:
        _log("КРИТИЧНО: не удалось получить my_id — авто-ответ невозможен")
        return {"replied": 0, "skipped": 0, "errors": 1, "contacts_sent": 0}
    _contacts_check = get_contacts(cookies, offset=0)
    if _contacts_check.get("_status") == 401:
        _log("Сессия истекла (401) — пропускаем задачу")
        return {"replied": 0, "skipped": 0, "errors": 0, "contacts_sent": 0}

    chats = task_get_all_chats_with_history(cookies, max_chats=max_chats, my_global_id=my_global_id)
    chats = [c for c in chats if c.get("last_role") == "user"]
    _log(f"Чатов для обработки: {len(chats)}")

    replied_user_ids = set()
    for chat in chats:
        if should_cancel_fn and should_cancel_fn():
            _log("Отмена получена")
            break

        user_id = chat["user_id"]
        history = chat["history"]
        name = chat["name"]

        if not history or history[-1]["role"] != "user":
            skipped += 1
            continue

        _log(f"{name}: генерирую ответ...")
        for i, msg in enumerate(history[-20:]):
            print(f"[VZN HISTORY] {name} [{i}] [{msg['role']}]: {msg['content'][:60]}", flush=True)

        try:
            reply = call_groq_fn(
                account_id=account_id,
                settings=settings,
                system_prompt=system_prompt,
                messages=history[-20:],
            )
        except Exception as e:
            _log(f"{name}: Groq ошибка: {e}")
            errors += 1
            continue

        if not reply:
            skipped += 1
            continue

        if should_cancel_fn and should_cancel_fn():
            break

        if user_id in replied_user_ids:
            skipped += 1
            continue

        time.sleep(2)
        fresh_resp2 = get_chat_history(cookies, user_id)
        fresh_msgs_raw2 = fresh_resp2.get("messagesItems") or []
        if isinstance(fresh_msgs_raw2, dict):
            fresh_all2 = []
            for uid2, msgs2 in fresh_msgs_raw2.items():
                if isinstance(msgs2, list):
                    fresh_all2.extend(msgs2)
            fresh_all2.sort(key=lambda m: m.get("datetime") or "", reverse=True)
        elif isinstance(fresh_msgs_raw2, list):
            fresh_all2 = sorted(fresh_msgs_raw2, key=lambda m: m.get("datetime") or "", reverse=True)
        else:
            fresh_all2 = []
        if fresh_all2:
            last_sender = str(fresh_all2[0].get("owner_id") or fresh_all2[0].get("sender_id") or "")
            if last_sender and last_sender != str(user_id):
                _log(f"{name}: уже ответили, пропускаю")
                skipped += 1
                continue

        try:
            if contacts and contacts.lower() in reply.lower():
                reply_without_contact = reply.replace(contacts, "").strip().strip("—-,. ")
                if reply_without_contact:
                    send_message(cookies, user_id, reply_without_contact)
                    time.sleep(1)
                    send_result = send_message(cookies, user_id, contacts)
                else:
                    send_message(cookies, user_id, "го в телегу?")
                    time.sleep(1)
                    send_result = send_message(cookies, user_id, contacts)
                status = send_result.get("_status")
                if status == 200:
                    replied += 1
                    replied_user_ids.add(user_id)
                    contacts_sent += 1
                    _log(f"{name}: ✓ контакт отправлен отдельно")
                else:
                    errors += 1
                    _log(f"{name}: ✗ ошибка отправки контакта: {send_result}")
            else:
                send_result = send_message(cookies, user_id, reply)
                status = send_result.get("_status")
                if status == 200:
                    replied += 1
                    replied_user_ids.add(user_id)
                    _log(f"{name}: ✓ ответ отправлен")
                    if contacts and any(x in reply.lower() for x in ["фото в тг", "скину в тг", "фото в телег"]):
                        time.sleep(1)
                        send_message(cookies, user_id, contacts)
                        contacts_sent += 1
                        _log(f"{name}: ✓ контакт отправлен после фото в тг")
                else:
                    errors += 1
                    _log(f"{name}: ✗ ошибка отправки: {send_result}")
        except Exception as e:
            errors += 1
            _log(f"{name}: ✗ исключение: {e}")
            continue

        time.sleep(2)

    return {
        "replied": replied,
        "skipped": skipped,
        "errors": errors,
        "contacts_sent": contacts_sent,
    }
