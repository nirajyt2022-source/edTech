import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def should_write_audit() -> bool:
    return os.getenv("ENABLE_ATTEMPT_AUDIT_DB", "0") == "1"


def write_attempt_event(payload: dict) -> None:
    """
    Best-effort: never raises.
    Writes to attempt_events in Supabase when ENABLE_ATTEMPT_AUDIT_DB=1.
    """
    if not should_write_audit():
        logger.debug("[audit.write_attempt_event] audit disabled (ENABLE_ATTEMPT_AUDIT_DB != 1)")
        return

    try:
        from app.services.supabase_client import get_supabase_client
        sb = get_supabase_client()
        sb.table("attempt_events").insert(payload).execute()
    except Exception as e:
        logger.error(f"[audit.write_attempt_event] {e}", exc_info=True)
        return
