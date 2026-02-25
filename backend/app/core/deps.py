import logging
from functools import lru_cache

from fastapi import HTTPException
from supabase import Client, create_client

from app.core.config import get_settings

logger = logging.getLogger("skolar.deps")


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)


def get_current_user_id(authorization: str) -> str:
    """Extract user_id from Supabase JWT token.

    Centralised auth helper — all routers should import this instead
    of maintaining their own ``get_user_id_from_token`` copy.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    try:
        sb = get_supabase_client()
        user_response = sb.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_response.user.id
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Auth verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Authentication failed")


def verify_child_ownership(user_id: str, child_id: str) -> None:
    """Raise 403 if *child_id* does not belong to *user_id*."""
    sb = get_supabase_client()
    result = sb.table("children").select("id").eq("id", child_id).eq("user_id", user_id).maybe_single().execute()
    if not getattr(result, "data", None):
        raise HTTPException(status_code=403, detail="Access denied")
