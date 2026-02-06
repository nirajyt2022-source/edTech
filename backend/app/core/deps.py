from functools import lru_cache
from supabase import create_client, Client
from openai import OpenAI
from app.core.config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)


@lru_cache
def get_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key)
