import os
from supabase import create_client

_client = None


def get_supabase_client():
    global _client
    if _client:
        return _client
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("Supabase env vars missing")
    _client = create_client(url, key)
    return _client
