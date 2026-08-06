# proxy_loader.py
import os
import httpx
from supabase import create_client
from supabase.client import ClientOptions

SUPABASE_URL = "https://uaknvfiuommbicpvwcql.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVha252Zml1b21tYmljcHZ3Y3FsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NTI5Mzk1MCwiZXhwIjoyMTAwODY5OTUwfQ.o_kjU1Z3Q__qoWg2jQ4U0eG3HDWX0dsmXvg-r7O4oE4"

_client = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(
    httpx_client=httpx.Client(http2=False, timeout=10.0)
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
