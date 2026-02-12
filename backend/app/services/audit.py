import os
import time
from typing import Any, Optional


def should_write_audit() -> bool:
    return os.getenv("ENABLE_ATTEMPT_AUDIT_DB", "0") == "1"


def write_attempt_event(payload: dict) -> None:
    """
    Best-effort: never raises.
    Writes to attempt_events in Supabase when ENABLE_ATTEMPT_AUDIT_DB=1.
    """
    if not should_write_audit():
        return

    try:
        from app.services.supabase_client import get_supabase_client
        sb = get_supabase_client()
        sb.table("attempt_events").insert(payload).execute()
    except Exception:
        # Never break API flow
        return
