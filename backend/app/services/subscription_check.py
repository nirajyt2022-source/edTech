"""Shared subscription enforcement for worksheet generation endpoints.

Usage:
    result = await check_and_increment_usage(user_id, supabase_client)
    if not result["allowed"]:
        raise HTTPException(status_code=402, detail=result["message"], ...)
"""

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("practicecraft.subscription")

FREE_TIER_LIMIT = 10  # worksheets per month


async def check_and_increment_usage(user_id: str, supabase_client) -> dict:
    """Check if user can generate a worksheet and increment usage.

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
        # 1. Query subscription row
        result = supabase_client.table("user_subscriptions") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        if not result.data:
            # No row — create one
            try:
                insert_result = supabase_client.table("user_subscriptions") \
                    .insert({
                        "user_id": user_id,
                        "tier": "free",
                        "worksheets_generated_this_month": 0,
                    }) \
                    .execute()
                sub = insert_result.data[0] if insert_result.data else None
            except Exception as insert_exc:
                logger.warning(
                    "Failed to create subscription row for user %s: %s",
                    user_id, insert_exc,
                )
                return _fail_open()

            if not sub:
                logger.warning("Insert returned no data for user %s", user_id)
                return _fail_open()
        else:
            sub = result.data[0]

        tier = sub.get("tier", "free")

        # 2. Paid tier — always allowed
        if tier == "paid":
            return {
                "allowed": True,
                "tier": "paid",
                "remaining": None,
                "message": "Paid tier — unlimited worksheets.",
            }

        # 3. Free tier — check month reset
        worksheets_used = sub.get("worksheets_generated_this_month", 0)
        month_reset_at_raw = sub.get("month_reset_at")

        if month_reset_at_raw:
            try:
                month_reset_at = datetime.fromisoformat(
                    str(month_reset_at_raw).replace("Z", "+00:00")
                )
                now = datetime.now(month_reset_at.tzinfo or timezone.utc)
                if now >= month_reset_at:
                    # Reset counter and advance month_reset_at to start of next month
                    next_reset = _start_of_next_month(now)
                    supabase_client.table("user_subscriptions") \
                        .update({
                            "worksheets_generated_this_month": 0,
                            "month_reset_at": next_reset.isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }) \
                        .eq("user_id", user_id) \
                        .execute()
                    worksheets_used = 0
            except (ValueError, TypeError) as parse_exc:
                logger.warning(
                    "Could not parse month_reset_at for user %s: %s",
                    user_id, parse_exc,
                )

        # 4. Check limit
        if worksheets_used >= FREE_TIER_LIMIT:
            return {
                "allowed": False,
                "tier": "free",
                "remaining": 0,
                "message": "Monthly limit reached. Upgrade to paid plan for unlimited worksheets.",
            }

        # 5. Increment counter
        new_count = worksheets_used + 1
        supabase_client.table("user_subscriptions") \
            .update({
                "worksheets_generated_this_month": new_count,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }) \
            .eq("user_id", user_id) \
            .execute()

        remaining = FREE_TIER_LIMIT - new_count
        return {
            "allowed": True,
            "tier": "free",
            "remaining": remaining,
            "message": f"Worksheet allowed. {remaining} remaining this month.",
        }

    except Exception as exc:
        logger.warning(
            "Subscription check failed for user %s (fail-open): %s",
            user_id, exc,
        )
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
