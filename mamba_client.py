"""
Mamba / Love Mail — HTTP клиент без Playwright.
Работает через куки напрямую — никакого браузера.
"""

import json
import re
import urllib.parse
import time
import base64
import gzip
from curl_cffi import requests as curl_requests

def _clean_text(s):
    """Убирает null-байты, которые ломают Postgres text-поля."""
    if not isinstance(s, str):
        return s
    return s.replace("\x00", "").replace("\u0000", "")

from typing import Optional


BASE_HOST = "love.mail.ru"
API_BASE      = "/mobile/api/v5.17.0.0"
API_BASE_POST = "/mobile/api/v5.17.0.0"
API_GRAPHQL = "/api/graphql/"
API_RATINGS = "/api/ratings/v2/voting/photos"

# ── Прокси настройки ──────────────────────────────────────
from proxy_loader import get_proxy as _get_proxy
def _proxy():
    return _get_proxy("mamba")


# ── Ключевые куки которые нужно вытащить при подключении анкеты ──────────────
REQUIRED_COOKIES = [
    "s_post",      # токен для отправки сообщений
    "mmbsid",      # сессия
    "UID",         # ID пользователя
    "mmbUID",      # ID пользователя (дубль)
    "SECRET",      # секрет авторизации
    "LOGIN",       # логин
]


def parse_cookies(raw: str) -> dict:
    """Парсит куки из строки Cookie-Editor JSON или строки name=value; ..."""
    raw = (raw or "").strip()
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return {
                item["name"]: item["value"]
                for item in parsed
                if item.get("name") and item.get("value") is not None
            }
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Fallback: строка name=value; name2=value2
    result = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            result[name.strip()] = value.strip()
    return result


def cookie_header(cookies: dict) -> str:
    """Собирает строку Cookie из словаря."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def extract_user_id(cookies: dict) -> Optional[str]:
    """Извлекает user_id из кук."""
    raw = (
        cookies.get("LOGIN") or
        cookies.get("mmbUID") or
        cookies.get("UID") or
        ""
    )
    return raw.replace("mb", "") if raw else None


def validate_cookies(cookies: dict) -> tuple[bool, list[str]]:
    """Проверяет наличие обязательных кук. Возвращает (ok, missing)."""
    missing = [k for k in REQUIRED_COOKIES if k not in cookies]
    return len(missing) == 0, missing


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _make_headers(cookies: dict, extra: dict = None) -> dict:
    headers = {
        "Accept":           "*/*",
        "Accept-Language":  "ru-RU,ru;q=0.9",
        "Accept-Encoding":  "gzip, deflate",
        "Connection":       "keep-alive",
        "Cookie":           cookie_header(cookies),
        "User-Agent": _proxy().get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Csrf-Token":       cookies.get("s_post", ""),
        "Mamba-Client":     '{"platform":"web","build":802}',
        "Mamba-Features":   '{"features":"0001000A000C0025000F000300100018001F00200023002400270029002A002B002D002E002F00320033003400360039","details":"00180007002A0002"}',
        "Content-Type":     "application/json",
        "Origin":           "https://love.mail.ru",
        "Referer":          "https://love.mail.ru/contact/list",
        "Sec-CH-UA": '"Google Chrome";v="149", "Chromium";v="149", "Not?A_Brand";v="24"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-CH-UA-Platform-Version": '"10.0.0"',
        "Upgrade-Insecure-Requests": "1",
        "sec-fetch-dest":   "empty",
        "sec-fetch-mode":   "cors",
        "sec-fetch-site":   "same-origin",
    }
    if extra:
        headers.update(extra)
    return headers


def _request(method: str, path: str, cookies: dict,
             body: str = None, extra_headers: dict = None,
             content_type: str = "application/json") -> dict:
    """Синхронный HTTP запрос к love.mail.ru через curl_cffi (Chrome TLS)."""

    headers = _make_headers(cookies, extra_headers)

    if body is not None:
        headers["Content-Type"] = content_type
    else:
        headers.pop("Content-Type", None)

    url = f"https://{BASE_HOST}{path}"

    p = _proxy()
    if p.get("use_proxy") and p.get("host"):
        proxy_url = f"http://{p['username']}:{p['password']}@{p['host']}:{p['port']}"
        proxies = {"https": proxy_url, "http": proxy_url}
    else:
        proxies = None

    print(f"Proxy: {p.get('host')}:{p.get('port')}" if p.get("use_proxy") else "No proxy")
    print("=" * 80)
    print("URL:", url)
    print("METHOD:", method)

    try:
        resp = curl_requests.request(
            method=method,
            url=url,
            headers=headers,
            data=body.encode("utf-8") if body else None,
            proxies=proxies,
            impersonate="chrome110",  # имитирует TLS fingerprint Chrome 110
            timeout=30,
            verify=False,
        )

        print("STATUS:", resp.status_code)

        raw = resp.content
        # curl_cffi сам распаковывает gzip — но на всякий случай
        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            text = ""

        try:
            data = json.loads(text)
        except Exception:
            data = {"_raw": text}

        data["_status"] = resp.status_code
        return data

    except Exception as e:
        print(f"[REQUEST ERROR] {e}", flush=True)
        return {"_status": 0, "_error": str(e)}

# ── Парсинг GraphQL ответов ───────────────────────────────────────────────────

def _parse_graphql_contact_nodes(resp: dict) -> list:
    """Извлекает nodes из ответа ContactsAndMatches GraphQL запроса."""
    nodes = (
        resp
        .get("data", {})
        .get("my", {})
        .get("messenger", {})
        .get("contactsList", {})
        .get("contacts", {})
        .get("nodes", [])
    )
    return nodes or []

def _parse_graphql_match_nodes(resp: dict) -> list:
    """Извлекает nodes из matchesList того же ответа ContactsAndMatches (мэтчи без сообщений)."""
    nodes = (
        resp
        .get("data", {})
        .get("my", {})
        .get("messenger", {})
        .get("matchesList", {})
        .get("contacts", {})
        .get("nodes", [])
    )
    return nodes or []

# ── API методы ────────────────────────────────────────────────────────────────

GRAPHQL_CONTACTS_QUERY = """query ContactsAndMatches($contactType: ContactType = ALL, $contactsAfter: Cursor, $matchesAfter: Cursor, $contactsLimit: Int, $matchesLimit: Int, $skipContacts: Boolean = false, $skipMatches: Boolean = false, $contactsFromChangeTime: Int, $matchesFromChangeTime: Int) {
  my {
    messenger {
      contactsList @skip(if: $skipContacts) {
        contacts(
          limit: $contactsLimit
          type: $contactType
          after: $contactsAfter
          fromChangeTime: $contactsFromChangeTime
        ) {
          nodes {
            ...ChatContactFragment
          }
          pageInfo {
            hasNextPage
            endCursor
          }
        }
      }
      matchesList: contactsList @skip(if: $skipMatches) {
        contacts(
          limit: $matchesLimit
          type: MATCH
          after: $matchesAfter
          fromChangeTime: $matchesFromChangeTime
        ) {
          nodes {
            contactId
            userId
            changeTime
            sortTime
            profile {
              id
              gender
              online {
                status
              }
              incognito
              photos {
                default {
                  id
                  urls {
                    squareSmall
                  }
                }
              }
              relations {
                contact {
                  favoriteByThem
                }
              }
            }
          }
          pageInfo {
            hasNextPage
            endCursor
          }
        }
      }
    }
  }
}
fragment ChatContactFragment on ChatContact {
  contactId
  userId
  changeTime
  sortTime
  superLike
  unreadReactions
  newMessagesCount
  messagesCount
  favorite
  support
  autoDeleteDate
  isMutedByMe
  isNewConversation
  historyWasErasedFrom
  lastMessage {
    postedAt
    new
    my
    text
    type
  }
  profile {
    id
    name
    gender
    verification {
      verifiedAccount
      verifiedPhotos
    }
    incognito
    deletedOnly
    banned
    bot
    online {
      status
    }
    photos {
      default {
        urls {
          squareSmall
        }
      }
    }
    age
    relations {
      contact {
        favoriteByThem
      }
    }
  }
}"""


def get_chats(cookies: dict, limit: int = 50, offset: int = 0) -> dict:
    """
    Получить список чатов через GraphQL.
    POST /api/graphql/?_loc[locale]=en
    """
    path = f"{API_GRAPHQL}?_loc[locale]=en"
    payload = json.dumps({
        "query": GRAPHQL_CONTACTS_QUERY,
        "variables": {
            "contactType": "ALL",
            "contactsLimit": limit,
            "matchesLimit": 100,
            "skipContacts": False,
            "skipMatches": False,
        },
        "operationName": "ContactsAndMatches",
    }, ensure_ascii=False)
    return _request("POST", path, cookies, body=payload)


def get_chat_messages(cookies: dict, interlocutor_id: str,
                      limit: int = 50, offset: int = 0) -> dict:
    """
    Получить историю сообщений с конкретным пользователем.
    GET /mobile/api/v5.17.0.0/users/{interlocutor_id}/chat?limit=50&offset=0
    """
    path = f"{API_BASE}/users/{interlocutor_id}/chat?limit={limit}&offset={offset}"
    return _request("GET", path, cookies)


def send_message(cookies: dict, to_anketa_id: str, message: str) -> dict:
    s_post = cookies.get("s_post", "")
    my_id  = extract_user_id(cookies)
    clean_id = str(to_anketa_id).replace("mb", "")
    path   = f"{API_BASE_POST}/users/{clean_id}/post"

    payload = json.dumps({
        "anketaId": int(str(my_id).replace("mb", "")),
        "message":  message,
        "s_post":   s_post,
    }, ensure_ascii=False)

    result = _request("POST", path, cookies, body=payload,
                      content_type="text/plain;charset=UTF-8")

    print(f"[SEND] to={to_anketa_id} my_id={my_id} status={result.get('_status')} resp={result}", flush=True)
    return result


def get_rating(cookies: dict, limit: int = 20) -> dict:
    """
    Получить анкеты для лайков через GraphQL.
    POST /api/graphql/?_loc[locale]=ru
    """
    path = f"{API_GRAPHQL}?_loc[locale]=ru"
    payload = json.dumps({
        "operationName": "Rating",
        "variables": {
            "ageFrom": 18,
            "ageTo": 99,
            "gender": "M",
            "heightFrom": 150,
            "heightTo": 220,
            "limit": limit,
            "location": "3159_4312_4400_0",
        },
        "query": "query Rating($ageFrom: Int!, $ageTo: Int!, $gender: String!, $heightFrom: Int, $heightTo: Int, $offsetPhotoId: Int, $location: String, $limit: Int!) {\n  photoRating {\n    queue(\n      ageFrom: $ageFrom\n      ageTo: $ageTo\n      gender: $gender\n      heightFrom: $heightFrom\n      heightTo: $heightTo\n      location: $location\n      offsetPhotoId: $offsetPhotoId\n      limit: $limit\n    ) {\n      photos {\n        photo {\n          photoId: id\n        }\n        photoOwner {\n          id\n          name\n          age\n        }\n      }\n      offsetPhotoId\n    }\n  }\n}",
    }, ensure_ascii=False)
    return _request("POST", path, cookies, body=payload)

def like_user(cookies: dict, photo_id: str) -> dict:
    """
    Поставить лайк по ID фото через правильный эндпоинт.
    """
    # Правильный эндпоинт — ratings API с photo_id
    path = f"/api/ratings/v2/voting/photos/{photo_id}/like?_loc%5Blocale%5D=ru"
    payload = json.dumps({"voteSource": 1}, ensure_ascii=False)
    result = _request("POST", path, cookies, body=payload)
    print(f"[LIKE] ratings status={result.get('_status')} response={json.dumps(result, ensure_ascii=False)[:300]}", flush=True)
    return result

    # Эндпоинт 2: старый API лайков
    path2 = f"{API_BASE}/users/{photo_id}/vote"
    payload2 = json.dumps({"vote": "1"}, ensure_ascii=False)
    result2 = _request("POST", path2, cookies, body=payload2)
    print(f"[LIKE] vote status={result2.get('_status')}", flush=True)
    if result2.get("_status") in (200, 201):
        return result2

    # Эндпоинт 3: через GraphQL мутацию
    path3 = f"{API_GRAPHQL}?_loc[locale]=ru"
    payload3 = json.dumps({
        "operationName": "VoteForUser",
        "variables": {"userId": int(photo_id), "vote": 1},
        "query": "mutation VoteForUser($userId: Int!, $vote: Int!) { voteForUser(userId: $userId, vote: $vote) { success } }"
    }, ensure_ascii=False)
    result3 = _request("POST", path3, cookies, body=payload3)
    print(f"[LIKE] graphql vote status={result3.get('_status')}", flush=True)
    print(f"[LIKE] graphql vote response={json.dumps(result3, ensure_ascii=False)[:500]}", flush=True)
    return result3

def task_likes_http(cookies: dict, limit: int = 20, log_fn=None) -> dict:
    """
    Поставить лайки через HTTP без Playwright.
    1. Получаем анкеты через get_rating (GraphQL)
    2. Ставим лайк каждой через like_user (REST)
    """
    status_check = detect_account_status(cookies)
    if status_check["status"] == "blocked":
        return {"liked": 0, "skipped": 0, "errors": 0, "blocked": True, "block_reason": status_check["reason"]}

    liked   = 0
    skipped = 0
    errors  = 0

    rating_resp = get_rating(cookies, limit=limit)
    photos = (
        rating_resp
        .get("data", {})
        .get("photoRating", {})
        .get("queue", {})
        .get("photos", [])
    )

    def _log(msg: str):
        print(f"[LIKES] {msg}", flush=True)
        if log_fn:
            try:
                log_fn(msg)
            except Exception:
                pass

    _log(f"Анкет для лайков найдено: {len(photos)}")
    if photos:
        _log(f"Пример первой анкеты: {json.dumps(photos[0], ensure_ascii=False)[:500]}")

    for idx, item in enumerate(photos, start=1):
        photo_id = str(item.get("photo", {}).get("photoId", "") or "")
        owner    = item.get("photoOwner", {}) or {}
        name     = owner.get("name") or photo_id or f"фото_{idx}"

        if not photo_id:
            skipped += 1
            continue

        try:
            result = like_user(cookies, photo_id)
            status = result.get("_status")
            if status in (200, 201):
                # Проверяем что нет ошибки в теле ответа
                if not result.get("errors") and result.get("_status") in (200, 201):
                    liked += 1
                else:
                    _log(f"[{idx}/{len(photos)}] ✗ {name}: ошибка в теле ответа: {result}")
                    errors += 1
                    continue
                _log(f"[{idx}/{len(photos)}] ✓ Лайк поставлен: {name}")
            else:
                _log(f"[{idx}/{len(photos)}] ✗ {name}: статус={status}")
                errors += 1
        except Exception as e:
            _log(f"[{idx}/{len(photos)}] ✗ {name}: ошибка {e}")
            errors += 1

    return {"liked": liked, "skipped": skipped, "errors": errors}

def get_matches(cookies: dict) -> dict:
    """
    Получить список матчей.
    GET /mobile/api/v5.17.0/users/{uid}/contacts/mutual
    """
    uid  = extract_user_id(cookies)
    path = f"{API_BASE}/users/{uid}/contacts/mutual"
    return _request("GET", path, cookies)



    result = _request("GET", path, cookies)
    
    # Дополнительно проверяем через лайк-эндпоинт — он возвращает 403+user_banned при блоке
    check_path = f"/api/ratings/v2/voting/photos/0/like?_loc%5Blocale%5D=ru"
    check_result = _request("POST", check_path, cookies, body='{"voteSource":1}')
    check_text = json.dumps(check_result, ensure_ascii=False, default=str).lower()
    if "user_banned" in check_text or "'blocking': true" in check_text or '"blocking": true' in check_text:
        result["_blocked_detected"] = True
        result["code"] = "user_banned"
        result["blocking"] = True
    
    return result


def _detect_account_status_raw(cookies: dict) -> dict:
    """
    Возвращает status:
    valid       — анкета работает;
    blocked     — анкета заблокирована;
    logged_out  — cookies больше не авторизованы;
    unknown     — временная или неизвестная ошибка.
    """
    try:
        response = check_session(cookies)
        print(f"[DETECT_STATUS DEBUG] http_status={response.get('_status')}", flush=True)
        print(f"[DETECT_STATUS DEBUG] raw={json.dumps(response, ensure_ascii=False, default=str)[:800]}", flush=True)
    except Exception as exc:
        return {
            "status": "unknown",
            "reason": f"Ошибка HTTP-проверки: {exc}",
            "http_status": 0,
        }

    http_status = int(response.get("_status") or 0)
    response_text = json.dumps(
        response,
        ensure_ascii=False,
        default=str,
    ).lower()

    blocked_markers = [
        '"banned": true',
        '"banned":true',
        "'code': 'user_banned'",
        '"code": "user_banned"',
        "user-banned",
        "'blocking': true",
        '"blocking": true',
        "'actionid': 'photo_verification'",
        '"actionid": "photo_verification"',
        "profile has been blocked",
        "account is blocked",
        "confirm photo",
        "подтвердите фото",
    ]

    if any(marker in response_text for marker in blocked_markers):
        return {
            "status": "blocked",
            "reason": "Анкета заблокирована или требует подтверждения фото",
            "http_status": http_status,
        }

    logged_out_markers = [
        "unauthorized",
        "not authorized",
        "not_authorized",
        "authentication required",
        "login required",
        "invalid session",
        "session expired",
        "invalid token",
        "войдите в аккаунт",
        "требуется авторизация",
        "сессия истекла",
    ]

    if http_status == 401 or any(
        marker in response_text for marker in logged_out_markers
    ):
        return {
            "status": "logged_out",
            "reason": "Cookies недействительны, анкета разлогинена",
            "http_status": http_status,
        }

    # Голый 403 без явных текстовых маркеров — не разлогин, а скорее
    # рейт-лимит/антибот/временная блокировка. Не трогаем session_valid.
    if http_status == 403:
        raw_text = response.get("_raw", "")
        if "variti" in str(raw_text).lower() or "<!doctype html" in str(raw_text).lower():
            return {
                "status": "unknown",
                "reason": "Variti антибот — IP прокси заблокирован, анкета жива",
                "http_status": http_status,
                "variti_block": True,
            }
        return {
            "status": "unknown",
            "reason": "HTTP 403 без явного маркера разлогина (временная ошибка?)",
            "http_status": http_status,
        }

    if 200 <= http_status < 300:
        return {
            "status": "valid",
            "reason": "Анкета активна",
            "http_status": http_status,
        }

    return {
        "status": "unknown",
        "reason": f"Неизвестный ответ сайта: HTTP {http_status}",
        "http_status": http_status,
    }

def detect_account_status(cookies: dict) -> dict:
    result = _detect_account_status_raw(cookies)
    if isinstance(result.get("reason"), str):
        result["reason"] = _clean_text(result["reason"])
    return result

def get_profile_photo(cookies: dict) -> Optional[str]:
    """Получает URL главного фото своей анкеты через GraphQL (my.photos.default.urls)."""
    path = f"{API_GRAPHQL}?_loc[locale]=ru"
    payload = json.dumps({
        "query": "query { my { photos { default { urls { squareLarge square squareSmall } } } } }"
    }, ensure_ascii=False)
    try:
        resp = _request("POST", path, cookies, body=payload)
        urls = (
            resp
            .get("data", {})
            .get("my", {})
            .get("photos", {})
            .get("default", {})
            .get("urls", {})
        )
        photo = urls.get("squareLarge") or urls.get("square") or urls.get("squareSmall")
        print(f"[PHOTO] Получено: {photo}", flush=True)
        return photo
    except Exception as e:
        print(f"[PHOTO] Ошибка: {e}", flush=True)
        return None

# ── Высокоуровневые задачи ────────────────────────────────────────────────────

def task_get_all_chats_with_history(cookies: dict, max_chats: int = 30) -> list[dict]:
    """
    Загружает список чатов через GraphQL и историю каждого через REST.
    Возвращает список словарей с историей для передачи в Groq.
    """
    result = []

    chats_resp = get_chats(cookies, limit=max_chats)
    nodes = _parse_graphql_contact_nodes(chats_resp)

    # Диагностика
    print(f"[API] GraphQL статус: {chats_resp.get('_status')}", flush=True)
    if chats_resp.get("errors"):
        print(f"[API] GraphQL ошибки: {chats_resp['errors']}", flush=True)
    if not nodes and chats_resp.get("_raw"):
        print(f"[API] Сырой ответ (первые 500): {str(chats_resp.get('_raw', ''))[:500]}", flush=True)

    print(f"[API] Чатов найдено: {len(nodes)}", flush=True)

    uid = extract_user_id(cookies)

    for node in nodes[:max_chats]:
        interlocutor_id = str(
            node.get("userId") or
            node.get("contactId") or
            node.get("profile", {}).get("id") or
            ""
        )
        if not interlocutor_id:
            continue

        profile = node.get("profile") or {}
        name    = profile.get("name") or interlocutor_id

        # Пропускаем заблокированных/удалённых
        if profile.get("banned") or profile.get("deletedOnly"):
            continue

        # Если вообще нет сообщений — пропускаем
        last_msg = node.get("lastMessage")
        if not last_msg:
            continue

        msgs_resp = get_chat_messages(cookies, interlocutor_id, limit=20)

        # Диагностика первого запроса истории
        if len(result) == 0:
            print(f"[API] get_chat_messages статус: {msgs_resp.get('_status')}", flush=True)
            if msgs_resp.get("_raw"):
                print(f"[API] get_chat_messages raw (первые 300): {str(msgs_resp.get('_raw', ''))[:300]}", flush=True)

        messages = (
            msgs_resp.get("messages") or
            msgs_resp.get("items") or
            msgs_resp.get("data") or
            []
        )

        history = []
        for msg in reversed(messages):
            # Пропускаем системные сообщения
            if msg.get("type") not in ("Message", "Photo"):
                continue
            msg_text    = msg.get("message") or msg.get("message_text") or ""
            is_incoming = msg.get("incoming", False)

            if not msg_text.strip():
                continue

            history.append({
                "role":    "user" if is_incoming else "assistant",
                "content": msg_text.strip(),
            })

        # Fallback: если REST не дал историю — берём lastMessage из GraphQL
        if not history and last_msg and last_msg.get("text"):
            is_my = last_msg.get("my", False)
            history.append({
                "role":    "assistant" if is_my else "user",
                "content": last_msg["text"].strip(),
            })

        if history:
            result.append({
                "interlocutor_id": interlocutor_id,
                "name":            name,
                "history":         history,
                "last_role":       history[-1]["role"] if history else None,
                "new_messages":    node.get("newMessagesCount", 0),
            })

    # ── Мэтчи без переписки — нужно написать первыми ──
    existing_ids = {r["interlocutor_id"] for r in result}
    match_nodes  = _parse_graphql_match_nodes(chats_resp)
    print(f"[API] Мэтчей без сообщений найдено: {len(match_nodes)}", flush=True)

    for node in match_nodes:
        interlocutor_id = str(
            node.get("userId") or
            node.get("contactId") or
            node.get("profile", {}).get("id") or
            ""
        )
        if not interlocutor_id or interlocutor_id in existing_ids:
            continue
        
         

        profile = node.get("profile") or {}
        if profile.get("banned") or profile.get("deletedOnly"):
            continue

        result.append({
            "interlocutor_id": interlocutor_id,
            "name":            profile.get("name") or interlocutor_id,
            "history":         [],
            "last_role":       None,
            "new_messages":    0,
            "is_new_match":    True,
        })

        if len(result) >= max_chats:
            break

    return result

def task_auto_reply_http(
    cookies: dict,
    settings: dict,
    build_prompt_fn,
    call_groq_fn,
    max_chats: int = 30,
    should_cancel_fn=None,
    telegram_was_sent_fn=None,
    reserve_telegram_send_fn=None,
    cancel_telegram_reservation_fn=None,
    log_fn=None,
) -> dict:

    status_check = detect_account_status(cookies)
    if status_check["status"] == "blocked":
        return {
            "replied": 0, "skipped": 0, "errors": 0, "contacts_sent": 0,
            "blocked": True, "block_reason": status_check["reason"],
        }

    account_id    = settings.get("_account_id", "")
    system_prompt = build_prompt_fn(settings)
    contacts      = (settings.get("contacts") or "").strip()

    replied        = 0
    skipped        = 0
    errors         = 0
    contacts_sent  = 0

    def _log(msg: str):
        print(f"[AUTO-REPLY] {msg}", flush=True)
        if log_fn:
            try:
                log_fn(msg)
            except Exception:
                pass

    chats = task_get_all_chats_with_history(cookies, max_chats=max_chats)
    _log(f"Найдено чатов для обработки: {len(chats)}")

    for chat in chats:
        # ← ПРОВЕРКА ОТМЕНЫ ПЕРЕД КАЖДЫМ ЧАТОМ
        if should_cancel_fn and should_cancel_fn():
            print(f"[AUTO-REPLY] Отмена получена, останавливаюсь", flush=True)
            break

        interlocutor_id = chat["interlocutor_id"]
        history         = chat["history"]
        name            = chat["name"]

        if contacts and telegram_was_sent_fn:
            try:
                if telegram_was_sent_fn(interlocutor_id, contacts):
                    print(
                        f"[AUTO-REPLY] {name}: этот Telegram уже отправлялся, пропускаю",
                        flush=True,
                    )
                    skipped += 1
                    continue
            except Exception as e:
                print(f"[AUTO-REPLY] Ошибка проверки Telegram: {e}", flush=True)
                errors += 1
                continue

        is_new_match = chat.get("is_new_match", False)

        if not is_new_match and (not history or history[-1]["role"] != "user"):
            skipped += 1
            continue

        # продолжаем отвечать даже если контакт уже отправлен

        # ← ПРОВЕРКА ПЕРЕД GROQ
        if should_cancel_fn and should_cancel_fn():
            break

        if is_new_match:
            _log(f"{name}: новый мэтч, пишу первой...")
            groq_messages = [{
                "role": "user",
                "content": "Напиши первое сообщение — просто поздоровайся коротко.",
            }]
        else:
            _log(f"{name}: генерирую ответ...")
            groq_messages = history[-20:]

        try:
            reply = call_groq_fn(
                account_id=account_id,
                settings=settings,
                system_prompt=system_prompt,
                messages=groq_messages,
            )
        except Exception as e:
            print(f"[AUTO-REPLY] Groq ошибка: {e}", flush=True)
            errors += 1
            continue

        if not reply:
            skipped += 1
            continue

        # ← ПРОВЕРКА ПЕРЕД ОТПРАВКОЙ
        if should_cancel_fn and should_cancel_fn():
            break

        reply_has_contact = bool(
            contacts and contacts.lower() in reply.lower()
        )
        reservation_created = False

        if reply_has_contact and reserve_telegram_send_fn:
            try:
                reservation_created = reserve_telegram_send_fn(
                    interlocutor_id,
                    contacts,
                    account_id,
                )
            except Exception as e:
                print(f"[AUTO-REPLY] Ошибка записи Telegram: {e}", flush=True)
                errors += 1
                continue

            if not reservation_created:
                print(
                    f"[AUTO-REPLY] {name}: Telegram уже отправлен другой анкетой",
                    flush=True,
                )
                skipped += 1
                continue

        try:
            send_result = send_message(cookies, interlocutor_id, reply)

            # задержка убрана

            status = send_result.get("_status")
            error_code = send_result.get("errorCode", 0)

            if status == 200 and error_code == 0:
                replied += 1
                _log(f"{name}: ✓ ответ отправлен" + (" (контакт передан)" if reply_has_contact else ""))
                if reply_has_contact:
                    contacts_sent += 1
            else:
                errors += 1
                print(f"[AUTO-REPLY] {name}: полный ответ при ошибке отправки: {send_result}", flush=True)
                _log(f"{name}: ✗ ошибка отправки (status={status}, errorCode={error_code})")
                if reservation_created and cancel_telegram_reservation_fn:
                    cancel_telegram_reservation_fn(
                        interlocutor_id,
                        contacts,
                        account_id,
                    )
        except Exception as e:
            errors += 1
            if reservation_created and cancel_telegram_reservation_fn:
                cancel_telegram_reservation_fn(
                    interlocutor_id,
                    contacts,
                    account_id,
                )

    return {
        "replied":       replied,
        "skipped":       skipped,
        "errors":        errors,
        "contacts_sent": contacts_sent,
    }
