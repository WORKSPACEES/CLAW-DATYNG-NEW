"""
Twinby — HTTP клиент без Playwright.
Работает через JWT токен напрямую.
"""
import random
import json
import re
import http.client
import gzip
import time
import uuid
from typing import Optional


BASE_HOST = "twinby.ru"
API_BASE = "/api"

from proxy_loader import get_proxy as _get_proxy
def _proxy():
    return _get_proxy("twinby")


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


def extract_jwt(cookies_or_token: dict | str) -> str:
    """Извлекает JWT токен из кук или строки."""
    if isinstance(cookies_or_token, str):
        raw = cookies_or_token.strip()
        # Если это JSON с полем token
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data.get("token") or data.get("jwt") or data.get("access_token") or ""
        except Exception:
            pass
        # Если это уже чистый JWT
        if raw.startswith("eyJ"):
            return raw
        # Может быть "JWT eyJ..." или "JWT {json}"
        if raw.upper().startswith("JWT "):
            after = raw[4:].strip()
            # after может быть JSON объектом
            try:
                data = json.loads(after)
                if isinstance(data, dict):
                    return data.get("token") or data.get("jwt") or data.get("access_token") or ""
            except Exception:
                pass
            if after.startswith("eyJ"):
                return after
            return after
        return raw
    if isinstance(cookies_or_token, dict):
        return (
            cookies_or_token.get("token") or
            cookies_or_token.get("jwt") or
            cookies_or_token.get("access_token") or
            ""
        )
    return ""


def _api_request(method: str, path: str, token: str, body: dict = None) -> dict:
    """Запрос к twinby.ru API."""
    headers = {
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Content-Type": "application/json",
        "Authorization": f"JWT {token}",
        "User-Agent": _proxy().get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
        "Origin": "https://twinby.ru",
        "Referer": "https://twinby.ru/",
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
            conn = http.client.HTTPSConnection(p["host"], p["port"], timeout=15)
            conn.set_tunnel(BASE_HOST, 443, {
                "Proxy-Authorization": f"Basic {auth}"
            })
        else:
            conn = http.client.HTTPSConnection(BASE_HOST, timeout=15)

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


# ── API методы ────────────────────────────────────────────

def get_me(token: str) -> dict:
    """Получить профиль текущего пользователя. GET /api/users/me/"""
    resp = _api_request("GET", f"{API_BASE}/users/me/", token)
    print(f"[TWINBY] get_me статус={resp.get('_status')}", flush=True)
    print(f"[TWINBY] get_me raw={str(resp)[:500]}", flush=True)
    return resp


def detect_account_status(token: str) -> dict:
    """Проверяет что токен живой."""
    resp = get_me(token)
    status = resp.get("_status", 0)

    if status in (200, 201):
        moderation = resp.get("moderationStatus")
        if moderation == 3:
            return {"status": "blocked", "reason": "Аккаунт заблокирован (moderationStatus=3)", "http_status": status}
        return {"status": "valid", "http_status": status}
    if status == 401:
        return {"status": "logged_out", "reason": "Токен недействителен", "http_status": status}
    if status == 403:
        return {"status": "blocked", "reason": "Аккаунт заблокирован (HTTP 403)", "http_status": status}
    if status == 0:
        return {"status": "error", "reason": resp.get("_error", "Нет соединения"), "http_status": 0}

    return {"status": "unknown", "reason": f"HTTP {status}", "http_status": status}


def get_profiles_for_likes(token: str, limit: int = 20) -> list[dict]:
    all_results = []
    page = 1
    while len(all_results) < limit:
        resp = _api_request("GET", f"{API_BASE}/dating/action/incoming/?page={page}&size=40", token)
        results = resp.get("results") or resp.get("data") or []
        if not results:
            break
        all_results.extend(results)
        if len(results) < 40:
            break
        page += 1
    print(f"[TWINBY] Входящих лайков: {len(all_results)}", flush=True)
    return all_results


def like_profile(token: str, user_id) -> dict:
    """
    Поставить лайк.
    POST /api/dating/action/from-search-action/
    Body: {"user": <user_id>, "type": 0}
    """
    resp = _api_request(
        "POST",
        f"{API_BASE}/dating/action/from-search-action/",
        token,
        body={"user": user_id, "type": 0}
    )
    print(f"[TWINBY] Лайк {user_id}: статус={resp.get('_status')}", flush=True)
    return resp


def get_chats(token: str, page: int = 1) -> dict:
    """
    Получить список чатов.
    GET /api/chats/list/
    """
    resp = _api_request("GET", f"{API_BASE}/chats/list/?page={page}", token)
    print(f"[TWINBY] get_chats статус={resp.get('_status')}", flush=True)
    return resp

def get_empty_chats(token: str, page: int = 1, size: int = 20) -> dict:
    """
    Получить список чатов без сообщений (новые матчи, которым ещё не писали).
    GET /api/chats/chat/empty/v2/
    """
    resp = _api_request("GET", f"{API_BASE}/chats/chat/empty/v2/?page={page}&size={size}", token)
    print(f"[TWINBY] get_empty_chats статус={resp.get('_status')}", flush=True)
    return resp

def get_lobby(token: str) -> dict:
    resp = _api_request("GET", f"{API_BASE}/chats/lobby-v2/lobby-main-list/", token)
    print(f"[TWINBY] get_lobby статус={resp.get('_status')}", flush=True)
    print(f"[TWINBY] get_lobby keys={list(resp.keys())}", flush=True)
    print(f"[TWINBY] get_lobby raw={str(resp)[:300]}", flush=True)
    return resp


def get_chat_messages(token: str, chat_id) -> dict:
    """
    Получить историю чата.
    GET /api/chats/chat/<chat_id>/message/
    """
    resp = _api_request("GET", f"{API_BASE}/chats/chat/{chat_id}/message/?page=1&size=50", token)
    print(f"[TWINBY] get_chat_messages {chat_id}: статус={resp.get('_status')}", flush=True)
    return resp


def send_message(token: str, chat_id, message: str) -> dict:
    """
    Отправить сообщение.
    POST /api/chats/chat/<chat_id>/message/
    Body: {"id": "<uuid>", "text": "<text>", "attaches": []}
    """
    body = {
        "id": str(uuid.uuid4()),
        "text": message,
        "attaches": [],
    }
    resp = _api_request(
        "POST",
        f"{API_BASE}/chats/chat/{chat_id}/message/",
        token,
        body=body
    )
    print(f"[TWINBY] send_message {chat_id}: статус={resp.get('_status')}", flush=True)
    return resp


# ── Высокоуровневые задачи ────────────────────────────────

def task_likes_http(token: str, limit: int = 20) -> dict:
    liked = 0
    skipped = 0
    errors = 0

    profiles = get_profiles_for_likes(token, limit=limit)

    if not profiles:
        print("[TWINBY LIKES] Нет анкет для лайков", flush=True)
        return {"liked": 0, "skipped": 0, "errors": 0}

    profiles = profiles[:limit]

    seen_users = set()

    for profile in profiles:
        user_obj = profile.get("user") or profile
        user_id = user_obj.get("id") or profile.get("user_id")
        action_id = profile.get("id")  # UUID входящего лайка
        name = user_obj.get("name") or str(user_id)

        if not user_id:
            skipped += 1
            continue

        if user_id in seen_users:
            print(f"[TWINBY LIKES] дубль {name}, пропускаю", flush=True)
            skipped += 1
            continue
        seen_users.add(user_id)

        try:
            result = like_profile(token, user_id)
            status = result.get("_status")
            if status in (200, 201):
                liked += 1
                print(f"[TWINBY LIKES] ✓ {name} ({user_id})", flush=True)
            elif status == 400 and "conflict" in str(result).lower():
                print(f"[TWINBY LIKES] уже лайкнут {name}, пропускаю", flush=True)
                skipped += 1
            else:
                print(f"[TWINBY LIKES] ✗ {name}: статус={status} {result}", flush=True)
                errors += 1
        except Exception as e:
            print(f"[TWINBY LIKES] ✗ {name}: {e}", flush=True)
            errors += 1

        time.sleep(random.uniform(1, 3))

    return {"liked": liked, "skipped": skipped, "errors": errors}


def task_get_all_chats_with_history(token: str, max_chats: int = 30) -> list[dict]:
    """Получает чаты с историей переписки."""

    # Берём чаты из /api/chats/list/
    chats_resp = get_chats(token)
    chats_raw = (
        chats_resp.get("results") or
        chats_resp.get("data") or
        []
    )

    # Дедупликация чатов по chat_id
    seen_chats = set()
    unique_chats = []
    for chat in chats_raw:
        chat_obj = chat.get("chat") or chat
        cid = chat_obj.get("id") or chat.get("chat_id")
        if cid and cid not in seen_chats:
            seen_chats.add(cid)
            unique_chats.append(chat)
    chats_raw = unique_chats

    print(f"[TWINBY] Чатов: {len(chats_raw)}", flush=True)

    result = []

    # Получаем свой ID один раз
    me = get_me(token)
    my_id = str(me.get("id") or me.get("user_id") or "")
    print(f"[TWINBY DEBUG] my_id={my_id}", flush=True)

    for chat in chats_raw[:max_chats]:
        chat_obj = chat.get("chat") or chat
        chat_id = chat_obj.get("id") or chat.get("chat_id")
        if not chat_id:
            continue

        companion = chat.get("companion") or chat.get("user") or {}
        name = companion.get("name") or companion.get("username") or str(chat_id)
        companion_id = companion.get("id")

        msgs_resp = get_chat_messages(token, chat_id)
        msgs_raw = msgs_resp.get("results") or msgs_resp.get("data") or []
        print(f"[TWINBY DEBUG] chat {chat_id} ({name}): получено сообщений из API = {len(msgs_raw)}", flush=True)

        if not msgs_raw:
            print(f"[TWINBY DEBUG] chat {chat_id}: пустая история", flush=True)
            continue

        # API возвращает от новых к старым — разворачиваем
        msgs_raw = list(reversed(msgs_raw))

        history = []
        for msg in msgs_raw:
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            owner_id = str(msg.get("ownerId") or msg.get("owner_id") or "")
            is_incoming = owner_id != my_id
            history.append({
                "role": "user" if is_incoming else "assistant",
                "content": text,
            })

        if not history:
            continue

        print(f"[TWINBY DEBUG] {name}: {len(history)} сообщ, последнее: [{history[-1]['role']}] {history[-1]['content'][:40]}", flush=True)

        result.append({
            "chat_id": chat_id,
            "name": name,
            "companion_id": companion_id,
            "history": history,
            "last_role": history[-1]["role"],
        })

    return result


def task_auto_reply_http(
    token: str,
    settings: dict,
    build_prompt_fn,
    call_groq_fn,
    max_chats: int = 5,
    should_cancel_fn=None,
) -> dict:
    """Авто-ответ для Twinby."""

    status_check = detect_account_status(token)
    if status_check["status"] == "blocked":
        return {"replied": 0, "skipped": 0, "errors": 0, "contacts_sent": 0,
                "blocked": True, "logged_out": False}
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
    greeted = 0

    # ── Пишем первым новым матчам ──────────────────────────
    try:
        matches_resp = get_empty_chats(token, page=1, size=20)
        print(f"[TWINBY MATCH] raw={str(matches_resp)[:500]}", flush=True)
        matches = matches_resp.get("results") or matches_resp.get("data") or []
        print(f"[TWINBY MATCH] Пустых чатов (новых матчей): {len(matches)}", flush=True)

        seen_chat_ids = set()
        unique_matches = []
        for m in matches:
            cid = (m.get("chat") or m).get("id") or m.get("chatId") or m.get("chat_id")
            if cid and cid not in seen_chat_ids:
                seen_chat_ids.add(cid)
                unique_matches.append(m)
        matches = unique_matches

        for match in matches:
            if should_cancel_fn and should_cancel_fn():
                break
            chat_obj = match.get("chat") or match
            companion = match.get("interlocutor") or match.get("companion") or match.get("user") or {}
            name = companion.get("name") or "Собеседник"
            chat_id = chat_obj.get("id") or match.get("chatId") or match.get("chat_id")
            if not chat_id:
                print(f"[TWINBY MATCH] {name}: нет chat_id. keys={list(match.keys())}", flush=True)
                continue

            msgs_resp = get_chat_messages(token, chat_id)
            msgs_raw = msgs_resp.get("results") or msgs_resp.get("data") or []
            if msgs_raw:
                continue

            try:
                _greetings = [
                    "приветик, как насчет познакомиться поближе и встретиться ?",
                    "салют, приколько выглядишь, составишь компания мне ? давай встретимся ? не хочу долго мусолить тут",
                    "куку, что рассматриваешь тут? было бы интересно встреться и провести время вместе ?",
                    "Привет, какие планы на вечер? давай встретимся ?",
                    "Вау, это что за тигр тут, встретиться не хочешь ?",
                    "привет, за встречи тут или просто общаться?",
                    "привет, встречи на мат основе интересуют ?",
                ]
                first_reply = random.choice(_greetings)
                print(f"[TWINBY MATCH] Выбрано приветствие: {first_reply}", flush=True)

                # ── Финальная проверка прямо перед отправкой ──
                recheck_resp = get_chat_messages(token, chat_id)
                recheck_raw = recheck_resp.get("results") or recheck_resp.get("data") or []
                if recheck_raw:
                    print(f"[TWINBY MATCH] {name}: уже ответили (параллельный запуск), пропускаю", flush=True)
                    continue

                # Сообщение 1 — приветствие
                send_result = send_message(token, chat_id, first_reply)
                if send_result.get("_status") not in (200, 201):
                    print(f"[TWINBY MATCH] ✗ {name}: {send_result}", flush=True)
                else:
                    print(f"[TWINBY MATCH] ✓ написал первым {name}: {first_reply[:50]}", flush=True)
                    time.sleep(random.uniform(2, 4))

                    # Сообщение 2 — предложение тг
                    _tg_openers = [
                        "го в телегу?",
                        "может в тг?",
                        "погнали в телегу?",
                        "мне тут не оч удобно, го в тг?",
                    ]
                    send_message(token, chat_id, random.choice(_tg_openers))
                    time.sleep(random.uniform(2, 4))

                    # Сообщение 3 — контакт
                    if contacts:
                        send_result3 = send_message(token, chat_id, contacts)
                        if send_result3.get("_status") in (200, 201):
                            contacts_sent += 1
                            print(f"[TWINBY MATCH] ✓ контакт отправлен {name}", flush=True)
                    greeted += 1

            except Exception as e:
                print(f"[TWINBY MATCH] ✗ {name}: {e}", flush=True)

            time.sleep(random.uniform(1, 3))

    except Exception as e:
        print(f"[TWINBY MATCH] ошибка: {e}", flush=True)

    # ── Отвечаем на входящие сообщения ────────────────────
    chats = task_get_all_chats_with_history(token, max_chats=max_chats)
    chats = [c for c in chats if c.get("last_role") == "user"]

    for chat in chats:
        if should_cancel_fn and should_cancel_fn():
            print("[TWINBY AUTO-REPLY] Отмена", flush=True)
            break

        chat_id = chat["chat_id"]
        history = chat["history"]
        name = chat["name"]

        if not history or history[-1]["role"] != "user":
            skipped += 1
            continue

        print(f"[TWINBY AUTO-REPLY] {name} (chat {chat_id}): генерирую...", flush=True)

        try:
            reply = call_groq_fn(
                account_id=account_id,
                settings=settings,
                system_prompt=system_prompt,
                messages=history[-20:],
            )
        except Exception as e:
            print(f"[TWINBY AUTO-REPLY] Groq ошибка: {e}", flush=True)
            errors += 1
            continue

        if not reply:
            skipped += 1
            continue

        if should_cancel_fn and should_cancel_fn():
            break

        # ── Страховка от дублей: перепроверяем перед отправкой ──
        fresh_resp = get_chat_messages(token, chat_id)
        fresh_msgs = fresh_resp.get("results") or fresh_resp.get("data") or []
        if fresh_msgs:
            last_owner = str(fresh_msgs[0].get("ownerId") or fresh_msgs[0].get("owner_id") or "")
            me = get_me(token)
            my_id = str(me.get("id") or me.get("user_id") or "")
            if last_owner == my_id:
                print(f"[TWINBY AUTO-REPLY] {name}: уже ответили (другой процесс), пропускаю", flush=True)
                skipped += 1
                continue

        try:
            if contacts and contacts.lower() in reply.lower():
                reply_without_contact = reply.replace(contacts, "").strip()
                reply_without_contact = reply_without_contact.strip("—-,. ")

                if reply_without_contact:
                    send_message(token, chat_id, reply_without_contact)
                    time.sleep(random.uniform(2, 4))

                send_result = send_message(token, chat_id, contacts)
                status = send_result.get("_status")
                if status in (200, 201):
                    replied += 1
                    contacts_sent += 1
                    print(f"[TWINBY AUTO-REPLY] {name}: ✓ контакт отправлен отдельно", flush=True)
                else:
                    errors += 1
            else:
                send_result = send_message(token, chat_id, reply)
                status = send_result.get("_status")
                if status in (200, 201):
                    replied += 1
                    print(f"[TWINBY AUTO-REPLY] {name}: ✓ ответ отправлен", flush=True)
                else:
                    errors += 1
                    print(f"[TWINBY AUTO-REPLY] {name}: ✗ {send_result}", flush=True)
        except Exception as e:
            errors += 1
            print(f"[TWINBY AUTO-REPLY] {name}: ✗ {e}", flush=True)
            continue

        time.sleep(random.uniform(1, 3))

    return {
        "replied": replied,
        "skipped": skipped,
        "errors": errors,
        "contacts_sent": contacts_sent,
        "greeted": greeted,
    }
