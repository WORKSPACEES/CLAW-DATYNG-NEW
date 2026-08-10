"""
worker_intcity.py — воркер CLAW-AI MANAGER для intCity.

Парсит объявления с intimcity.co и делает рассылку на email.
Запуск:
    python worker_intcity.py
"""

import asyncio
import os
import json
import re
from datetime import datetime
from pathlib import Path

import httpx
from supabase import create_client, Client
from supabase.client import ClientOptions

import aiohttp

# ══════════════════════════════════════════════════════════
# КОНФИГ
# ══════════════════════════════════════════════════════════

SUPABASE_URL = "https://uaknvfiuommbicpvwcql.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVha252Zml1b21tYmljcHZ3Y3FsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NTI5Mzk1MCwiZXhwIjoyMTAwODY5OTUwfQ.o_kjU1Z3Q__qoWg2jQ4U0eG3HDWX0dsmXvg-r7O4oE4"

MAX_CONCURRENT_JOBS = 10
POLL_INTERVAL = 2

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── Supabase client ──
_supabase_http_client = httpx.Client(http2=False, timeout=30.0)
supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=ClientOptions(httpx_client=_supabase_http_client),
)

CANCEL_FLAGS: dict[str, bool] = {}
ACTIVE_JOB_IDS: dict[str, str] = {}
JOB_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


def should_cancel(account_id: str) -> bool:
    return CANCEL_FLAGS.get(account_id, False)


# ══════════════════════════════════════════════════════════
# KEEP-ALIVE / HEALTH SERVER
# ══════════════════════════════════════════════════════════

async def keep_alive():
    await asyncio.sleep(30)
    while True:
        try:
            port = int(os.environ.get("PORT", 10005))
            async with aiohttp.ClientSession() as session:
                await session.get(f"http://localhost:{port}/health", timeout=aiohttp.ClientTimeout(total=10))
                print("[WORKER-INTCITY] Keep-alive ping OK", flush=True)
        except Exception as e:
            print(f"[WORKER-INTCITY] Keep-alive ping failed: {e}", flush=True)
        await asyncio.sleep(240)


async def start_dummy_server():
    from aiohttp import web
    app = web.Application()
    app.router.add_get("/health", lambda r: web.Response(text="OK"))
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10005))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[WORKER-INTCITY] Health server на порту {port}", flush=True)


# ══════════════════════════════════════════════════════════
# SUPABASE HELPERS
# ══════════════════════════════════════════════════════════

def get_intcity_account_ids() -> list[str]:
    try:
        res = supabase.table("accounts").select("id").eq("platform", "intCity").execute()
        return [r["id"] for r in (res.data or [])]
    except Exception:
        return []


def get_account_creds(account_id: str) -> dict:
    """Достаёт email и пароль из accounts_private."""
    try:
        res = supabase.table("accounts_private").select("cookies_raw").eq("id", account_id).execute()
        if res.data:
            return json.loads(res.data[0].get("cookies_raw", "{}"))
    except Exception:
        pass
    return {}


def get_ai_settings(account_id: str) -> dict:
    """Достаёт настройки рассылки из ai_settings."""
    try:
        res = supabase.table("ai_settings").select("*").eq("account_id", account_id).execute()
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return {}


def get_owner_email(account_id: str) -> str:
    try:
        res = supabase.table("accounts").select("owner_email").eq("id", account_id).execute()
        if res.data:
            return res.data[0].get("owner_email", "")
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════
# ПАРСИНГ intimcity.co
# ══════════════════════════════════════════════════════════

async def parse_intcity(pages: int = 3) -> list[dict]:
    BASE_URL = "https://a.intimcity.co"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://a.intimcity.co/bullboard",
    }

    found = []

    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True) as client:
        for page in range(1, pages + 1):
            try:
                url = f"{BASE_URL}/bullboard?gender_from=m&gender_to=f&place=&page={page}"
                resp = await client.get(url)
                html = resp.text

                # Берём всё содержимое data-bbcontact, потом вытаскиваем email
                bb_contacts = re.findall(r'data-bbcontact="([^"]*)"', html)
                email_pattern = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
                page_emails = 0
                for contact in bb_contacts:
                    emails_in_contact = email_pattern.findall(contact)
                    for email in emails_in_contact:
                        email = email.strip().lower()
                        if email and not any(x in email for x in ["intimcity", "example", "sentry", "test"]):
                            found.append({"email": email, "ad_url": url})
                            page_emails += 1

                print(f"[INTCITY] Страница {page}: {page_emails} валидных email из {len(bb_contacts)} контактов", flush=True)

            except Exception as e:
                print(f"[INTCITY] Ошибка страницы {page}: {e}", flush=True)

    # Дедупликация
    seen = set()
    unique = []
    for item in found:
        if item["email"] not in seen:
            seen.add(item["email"])
            unique.append(item)

    print(f"[INTCITY] Всего уникальных email: {len(unique)}", flush=True)
    return unique


def save_leads(found: list[dict], owner_email: str) -> int:
    """Сохраняет новые email в intcity_leads, возвращает кол-во новых."""
    saved = 0
    for item in found:
        try:
            supabase.table("intcity_leads").upsert({
                "email": item["email"],
                "ad_url": item["ad_url"],
                "owner_email": owner_email,
            }, on_conflict="email").execute()
            saved += 1
        except Exception as e:
            print(f"[INTCITY] save_leads ошибка: {e}", flush=True)
    return saved


def get_unsent_leads(owner_email: str, limit: int = 100) -> list[dict]:
    """Возвращает лиды которым ещё не отправляли письма."""
    try:
        res = (
            supabase.table("intcity_leads")
            .select("*")
            .eq("owner_email", owner_email)
            .is_("sent_at", "null")
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def mark_as_sent(lead_id: int):
    try:
        supabase.table("intcity_leads").update({
            "sent_at": datetime.now().isoformat()
        }).eq("id", lead_id).execute()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
# РАССЫЛКА
# ══════════════════════════════════════════════════════════

def send_emails(
    sender_email: str,
    sender_password: str,
    leads: list[dict],
    subject: str,
    body: str,
    mail_cookie: str = "",
    mail_token: str = "",
) -> dict:
    """Отправляет письма через mail.ru web API."""
    sent = 0
    errors = []

    if not mail_cookie or not mail_token:
        return {"ok": False, "sent": 0, "error": "Нет cookie/token — вставь их на карточке intCity"}

    # Парсим cookie — поддерживаем и JSON от Cookie Editor, и сырую строку
    cookie_str = mail_cookie.strip()
    if cookie_str.startswith("["):
        try:
            cookie_list = json.loads(cookie_str)
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookie_list if c.get("name") and c.get("value"))
            print(f"[INTCITY] Cookie собран из JSON: {len(cookie_list)} кук", flush=True)
        except Exception as e:
            print(f"[INTCITY] Ошибка парсинга cookie JSON: {e}", flush=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": cookie_str,
    }

    for lead in leads:
        try:
            # Пропускаем невалидные email
            if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', lead["email"]):
                print(f"[INTCITY] Пропуск невалидного: {lead['email']}", flush=True)
                mark_as_sent(lead["id"])
                continue
            import time as _time
            _time.sleep(2)
            import urllib.parse, uuid
            params = {
                "id": uuid.uuid4().hex,
                "source": '{"draft":"","reply":"","forward":"","schedule":""}',
                "headers": "{}",
                "template": "0",
                "sign": "0",
                "remind": "0",
                "delivery_report": "false",
                "receipt": "false",
                "subject": subject,
                "priority": "3",
                "send_date": "",
                "body": f'{{"html":"{body}","text":"{body}"}}',
                "from": f"{sender_email} <{sender_email}>",
                "correspondents": f'{{"to":"{lead["email"]}","cc":"","bcc":"","reply_to":""}}',
                "folder_id": "",
                "email": sender_email,
                "htmlencoded": "false",
                "token": mail_token,
                "attaches": '{"list":[]}',
                "delay_for_cancellation": "true",
            }
            resp = httpx.post(
                "https://e.mail.ru/api/v1/messages/send",
                headers=headers,
                content=urllib.parse.urlencode(params),
                timeout=20,
                follow_redirects=True,
            )
            print(f"[INTCITY] mail.ru status={resp.status_code} body={resp.text[:200]}", flush=True)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok" or data.get("id"):
                    mark_as_sent(lead["id"])
                    sent += 1
                    print(f"[INTCITY] ✓ Отправлено → {lead['email']}", flush=True)
                else:
                    err = str(data)[:100]
                    errors.append(f"{lead['email']}: {err}")
                    print(f"[INTCITY] ✗ API ошибка → {lead['email']}: {err}", flush=True)
            else:
                errors.append(f"{lead['email']}: HTTP {resp.status_code}")
                print(f"[INTCITY] ✗ HTTP {resp.status_code} → {lead['email']}", flush=True)
        except Exception as e:
            errors.append(f"{lead['email']}: {e}")
            print(f"[INTCITY] ✗ Исключение → {lead['email']}: {e}", flush=True)
            import time as _time
            _time.sleep(2)

    return {"ok": True, "sent": sent, "errors": errors}


# ══════════════════════════════════════════════════════════
# ОСНОВНАЯ ЗАДАЧА
# ══════════════════════════════════════════════════════════

def task_intcity_split(account_id: str, settings: dict, should_cancel_fn) -> dict:
    """
    Одна итерация сплита:
    1. Парсим новые объявления
    2. Сохраняем новые email
    3. Отправляем письма на неотправленные
    """
    creds = get_account_creds(account_id)
    mail_cookie = creds.get("mail_cookie", "") or ""
    mail_token = creds.get("mail_token", "") or ""

    # Email берём из Mpop куки
    sender_email = creds.get("email", "") or ""
    if not sender_email and "Mpop=" in mail_cookie:
        try:
            mpop = [c for c in mail_cookie.split("; ") if c.startswith("Mpop=")]
            if mpop:
                val = mpop[0].split("=", 1)[1]
                parts = val.split("%3A") if "%3A" in val else val.split(":")
                sender_email = parts[2] if len(parts) > 2 else ""
        except Exception:
            pass

    if not mail_cookie or not mail_token:
        return {"ok": False, "error": "Нет cookie/token", "summary": "Ошибка: нет cookie/token"}

    subject = settings.get("goal", "") or "Привет с intimcity"
    body = settings.get("persona", "") or "Привет! Увидел(а) ваше объявление на intimcity. Напишите мне!"
    pages = int(settings.get("bot_age", "3") or "3")
    mail_token = settings.get("stop_topics", "") or ""
    # Если нет — берём авто-полученные при подключении из cookies_raw
    if not mail_cookie or not mail_token:
        creds_full = get_account_creds(account_id)
        if not mail_cookie:
            mail_cookie = creds_full.get("mail_cookie", "") or ""
        if not mail_token:
            mail_token = creds_full.get("mail_token", "") or ""

    owner_email = get_owner_email(account_id)
    if not owner_email:
        return {"ok": False, "error": "owner_email не найден", "summary": "Ошибка аккаунта"}

    if should_cancel_fn():
        return {"ok": True, "status": "stopped_by_user", "summary": "Остановлено"}

    # Парсим
    print(f"[INTCITY] Парсим {pages} страниц...", flush=True)
    loop = asyncio.new_event_loop()
    found = loop.run_until_complete(parse_intcity(pages=pages))
    loop.close()

    if should_cancel_fn():
        return {"ok": True, "status": "stopped_by_user", "summary": "Остановлено"}

    # Сохраняем
    saved = save_leads(found, owner_email)
    print(f"[INTCITY] Сохранено новых: {saved}", flush=True)

    # Получаем неотправленных
    leads = get_unsent_leads(owner_email, limit=50)
    print(f"[INTCITY] Неотправленных лидов: {len(leads)}", flush=True)

    if not leads:
        return {
            "ok": True,
            "parsed": len(found),
            "saved": saved,
            "sent": 0,
            "summary": f"Спарсено {len(found)} email, новых нет — все уже получили письмо"
        }

    if should_cancel_fn():
        return {"ok": True, "status": "stopped_by_user", "summary": "Остановлено"}

    # Отправляем
    print(f"[INTCITY] Запускаем send_emails: sender={sender_email!r}, leads={len(leads)}", flush=True)
    result = send_emails(sender_email, "", leads, subject, body, mail_cookie, mail_token)
    print(f"[INTCITY] send_emails результат: {result}", flush=True)

    return {
        "ok": result["ok"],
        "parsed": len(found),
        "saved": saved,
        "sent": result.get("sent", 0),
        "errors": result.get("errors", [])[:5],
        "summary": f"Спарсено {len(found)}, сохранено {saved}, отправлено {result.get('sent', 0)}"
    }


# ══════════════════════════════════════════════════════════
# JOB QUEUE
# ══════════════════════════════════════════════════════════

async def claim_next_job() -> dict | None:
    intcity_ids = get_intcity_account_ids()
    if not intcity_ids:
        return None
    try:
        res = (
            supabase.table("job_queue")
            .select("*")
            .eq("status", "pending")
            .in_("account_id", intcity_ids)
            .order("created_at")
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        job = res.data[0]
        upd = supabase.table("job_queue").update({
            "status": "running",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", job["id"]).eq("status", "pending").execute()
        if not upd.data:
            return None
        return job
    except Exception as e:
        print(f"[WORKER-INTCITY] claim_next_job error: {e}", flush=True)
        return None


async def finish_job(job_id: str, result: dict, status: str = "done"):
    try:
        supabase.table("job_queue").update({
            "status": status,
            "result": result,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", job_id).execute()
    except Exception as e:
        print(f"[WORKER-INTCITY] finish_job error: {e}", flush=True)


async def heartbeat_job(job_id: str, interval: int = 10):
    while True:
        await asyncio.sleep(interval)
        try:
            res = supabase.table("job_queue").select("status, account_id").eq("id", job_id).execute()
            if not res.data:
                break
            row = res.data[0]
            status = row.get("status")
            account_id = row.get("account_id")

            if status == "cancelled":
                print(f"[WORKER-INTCITY] Задача {job_id} отменена", flush=True)
                CANCEL_FLAGS[account_id] = True
                break

            if status == "running":
                supabase.table("job_queue").update(
                    {"updated_at": datetime.utcnow().isoformat()}
                ).eq("id", job_id).execute()
        except Exception as e:
            print(f"[WORKER-INTCITY] Heartbeat ошибка: {e}", flush=True)


async def process_job(job: dict):
    async with JOB_SEMAPHORE:
        job_id = job["id"]
        account_id = job["account_id"]

        if account_id in ACTIVE_JOB_IDS:
            await finish_job(job_id, {"ok": True, "summary": "Отложено: уже выполняется"}, status="pending")
            return

        ACTIVE_JOB_IDS[account_id] = job_id
        CANCEL_FLAGS[account_id] = False

        print(f"\n[WORKER-INTCITY] Задача {job_id} для {account_id}", flush=True)
        hb_task = asyncio.create_task(heartbeat_job(job_id))

        try:
            job_type = job.get("type", "intcity-split")
            settings = get_ai_settings(account_id)

            if job_type != "intcity-split":
                await finish_job(job_id, {"ok": False, "error": f"Неизвестный тип: {job_type}"}, status="error")
                return

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: task_intcity_split(
                    account_id=account_id,
                    settings=settings,
                    should_cancel_fn=lambda: should_cancel(account_id),
                )
            )

            final_status = "cancelled" if result.get("status") == "stopped_by_user" else "done"
            await finish_job(job_id, result, status=final_status)

            # Создаём новую задачу для следующего круга (каждые 5 минут)
            if final_status == "done":
                await asyncio.sleep(5 * 60)
                supabase.table("job_queue").insert({
                    "account_id": account_id,
                    "platform": "intCity",
                    "type": "intcity-split",
                    "status": "pending",
                    "payload": job.get("payload", {}),
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }).execute()
                print(f"[WORKER-INTCITY] Новый круг запущен для {account_id}", flush=True)
            print(f"[WORKER-INTCITY] Задача {job_id} завершена: {result.get('summary')}", flush=True)

        except Exception as e:
            await finish_job(job_id, {"ok": False, "error": str(e), "summary": f"Ошибка: {e}"}, status="error")
            print(f"[WORKER-INTCITY] Задача {job_id} упала: {e}", flush=True)

        finally:
            hb_task.cancel()
            ACTIVE_JOB_IDS.pop(account_id, None)
            CANCEL_FLAGS.pop(account_id, None)


async def recover_interrupted_jobs():
    try:
        intcity_ids = get_intcity_account_ids()
        if not intcity_ids:
            return
        res = (
            supabase.table("job_queue")
            .update({"status": "pending", "result": None})
            .eq("status", "running")
            .in_("account_id", intcity_ids)
            .execute()
        )
        count = len(res.data or [])
        if count:
            print(f"[WORKER-INTCITY] Возвращено зависших задач: {count}", flush=True)
    except Exception as e:
        print(f"[WORKER-INTCITY] Ошибка восстановления: {e}", flush=True)


async def worker_loop():
    await recover_interrupted_jobs()
    print(f"[WORKER-INTCITY] Запущен. Опрашиваю очередь каждые {POLL_INTERVAL}с", flush=True)

    running_tasks: set[asyncio.Task] = set()

    while True:
        running_tasks = {t for t in running_tasks if not t.done()}
        free_slots = MAX_CONCURRENT_JOBS - len(running_tasks)

        for _ in range(free_slots):
            try:
                job = await claim_next_job()
            except Exception as e:
                print(f"[WORKER-INTCITY] Ошибка опроса: {e}", flush=True)
                job = None

            if not job:
                break

            task = asyncio.create_task(process_job(job))
            running_tasks.add(task)

        await asyncio.sleep(POLL_INTERVAL)


async def main():
    await start_dummy_server()
    await asyncio.gather(
        worker_loop(),
        keep_alive(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[WORKER-INTCITY] Остановлен.", flush=True)
