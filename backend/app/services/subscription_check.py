"""Shared subscription enforcement for worksheet generation endpoints.

Usage:
    result = await check_and_increment_usage(user_id, supabase_client)
    if not result["allowed"]:
        raise HTTPException(status_code=402, detail=result["message"], ...)
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("skolar.subscription")

FREE_TIER_LIMIT = 10  # worksheets per month


async def check_and_increment_usage(user_id: str, supabase_client) -> dict:
    """Atomically check and increment worksheet usage via Postgres function.

    Returns:
        {
            "allowed": True/False,
            "tier": "free"/"paid",
            "remaining": int | None,   # None for paid (unlimited)
            "message": str,
        }

    On ANY DB error: logs warning and returns allowed=True (fail-open).
    """
    try:
        result = supabase_client.rpc(
            "increment_worksheet_usage",
            {"p_user_id": user_id, "p_limit": FREE_TIER_LIMIT}
        ).execute()

        if result.data:
            data = result.data
            if isinstance(data, list):
                data = data[0] if data else {}
            return {
                "allowed": data.get("allowed", True),
                "tier": data.get("tier", "unknown"),
                "remaining": data.get("remaining"),
                "message": data.get("message", ""),
            }
        return _fail_open()

    except Exception as exc:
        logger.warning("Subscription check failed (fail-open): %s", exc)
        return _fail_open()


def _fail_open() -> dict:
    """Return an allow-by-default response when DB is unreachable."""
    return {
        "allowed": True,
        "tier": "unknown",
        "remaining": None,
        "message": "Subscription check unavailable — allowing generation.",
    }


def _start_of_next_month(now: datetime) -> datetime:
    """Return the first day of the next month, preserving tzinfo."""
    if now.month == 12:
        return now.replace(year=now.year + 1, month=1, day=1,
                           hour=0, minute=0, second=0, microsecond=0)
    return now.replace(month=now.month + 1, day=1,
                       hour=0, minute=0, second=0, microsecond=0)
