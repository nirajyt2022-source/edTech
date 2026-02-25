"""Shared subscription enforcement for worksheet generation endpoints.

Usage:
    result = await check_and_increment_usage(user_id, supabase_client)
    if not result["allowed"]:
        raise HTTPException(status_code=402, detail=result["message"], ...)
"""

import logging
from datetime import datetime

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

    On ANY DB error: logs warning and returns allowed=False (fail-closed).
    """
    try:
        result = supabase_client.rpc(
            "increment_worksheet_usage", {"p_user_id": user_id, "p_limit": FREE_TIER_LIMIT}
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
        return _fail_closed()

    except Exception as exc:
        logger.warning("Subscription check failed (fail-closed): %s", exc)
        return _fail_closed()


def _fail_closed() -> dict:
    """Return a deny-by-default response when DB is unreachable."""
    return {
        "allowed": False,
        "tier": "unknown",
        "remaining": None,
        "message": "Service temporarily unavailable. Please try again.",
    }


async def check_ai_usage_allowed(user_id: str, supabase_client) -> dict:
    """Lightweight gate for non-worksheet AI endpoints (flashcards, revision, etc.).

    Paid users are always allowed. Free users are allowed up to
    FREE_TIER_LIMIT AI calls per month (same budget as worksheets).
    On DB failure: fail-closed.
    """
    try:
        result = (
            supabase_client.table("user_subscriptions")
            .select("tier, worksheets_generated_this_month")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        data = getattr(result, "data", None)
        if not data:
            # No subscription record yet — allow (first-time user)
            return {"allowed": True, "tier": "free", "message": ""}

        if data.get("tier") == "paid":
            return {"allowed": True, "tier": "paid", "message": ""}

        used = data.get("worksheets_generated_this_month", 0)
        if used >= FREE_TIER_LIMIT:
            return {
                "allowed": False,
                "tier": "free",
                "message": f"Free tier limit reached ({FREE_TIER_LIMIT}/month). Upgrade to continue.",
            }
        return {"allowed": True, "tier": "free", "message": ""}

    except Exception as exc:
        logger.warning("AI usage check failed (fail-closed): %s", exc)
        return _fail_closed()


def _start_of_next_month(now: datetime) -> datetime:
    """Return the first day of the next month, preserving tzinfo."""
    if now.month == 12:
        return now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
