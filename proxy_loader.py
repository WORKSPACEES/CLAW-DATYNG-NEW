# proxy_loader.py
import os
import httpx
from supabase import create_client
from supabase.client import ClientOptions

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://tbgaahpybvmfmzddrrdv.supabase.co")
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRiZ2FhaHB5YnZtZm16ZGRycmR2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDkzMDksImV4cCI6MjA5NzE4NTMwOX0.mnF7po7rusq3XrDIdfTuzuK8vXVkpMkJRWWT7QVVf2c"

_client = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(
    httpx_client=httpx.Client(http2=False, timeout=3.0)
))

_cache = {}
_cache_ttl = 60  # секунд
import time

def get_proxy(platform: str) -> dict:
    """Возвращает прокси для платформы из Supabase. Кэш 60 сек."""
    now = time.time()
    if platform in _cache and now - _cache[platform]["_ts"] < _cache_ttl:
        return _cache[platform]

    try:
        res = _client.table("proxy_settings").select("*").eq("id", platform).execute()
        if res.data:
            row = res.data[0]
            row["_ts"] = now
            _cache[platform] = row
            return row
    except Exception as e:
        print(f"[PROXY] Ошибка загрузки прокси для {platform}: {e}")

    # Фолбек — пустой прокси
    return {"use_proxy": False, "_ts": now}
