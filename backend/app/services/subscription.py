from datetime import datetime, timedelta
from fastapi import HTTPException
from supabase import Client

FREE_TIER_LIMIT = 3

def check_can_generate(supabase: Client, user_id: str) -> tuple[bool, str, dict]:
    """Check if user can generate a worksheet. Returns (can_generate, tier, subscription_data)."""
    result = supabase.table("user_subscriptions") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if not result.data:
        # Create subscription if doesn't exist
        insert_result = supabase.table("user_subscriptions") \
            .insert({"user_id": user_id, "tier": "free", "worksheets_generated_this_month": 0}) \
            .execute()
        sub = insert_result.data[0] if insert_result.data else {"tier": "free", "worksheets_generated_this_month": 0}
    else:
        sub = result.data[0]

    if sub["tier"] == "paid":
        return True, "paid", sub

    remaining = FREE_TIER_LIMIT - sub.get("worksheets_generated_this_month", 0)
    return remaining > 0, "free", sub

def increment_usage(supabase: Client, user_id: str, sub: dict) -> None:
    """Increment usage for free tier users."""
    if sub.get("tier") == "paid":
        return

    new_count = sub.get("worksheets_generated_this_month", 0) + 1
    supabase.table("user_subscriptions") \
        .update({
            "worksheets_generated_this_month": new_count,
            "updated_at": datetime.now().isoformat()
        }) \
        .eq("user_id", user_id) \
        .execute()

def ensure_subscription_exists(supabase: Client, user_id: str) -> dict:
    """Ensure user has a subscription record, create if not exists."""
    result = supabase.table("user_subscriptions") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if result.data and len(result.data) > 0:
        sub = result.data[0]
        # Check if we need to reset monthly count
        month_reset_at_str = sub["month_reset_at"]
        if month_reset_at_str:
            month_reset_at = datetime.fromisoformat(month_reset_at_str.replace("Z", "+00:00"))
            if datetime.now(month_reset_at.tzinfo) >= month_reset_at:
                # Reset the monthly count
                new_reset = (datetime.now().replace(day=1) + timedelta(days=32)).replace(day=1)
                update_result = supabase.table("user_subscriptions") \
                    .update({
                        "worksheets_generated_this_month": 0,
                        "month_reset_at": new_reset.isoformat(),
                        "updated_at": datetime.now().isoformat()
                    }) \
                    .eq("user_id", user_id) \
                    .execute()
                if update_result.data:
                    return update_result.data[0]
        return sub
    else:
        # Create new subscription
        insert_result = supabase.table("user_subscriptions") \
            .insert({
                "user_id": user_id,
                "tier": "free",
                "worksheets_generated_this_month": 0,
            }) \
            .execute()
        if insert_result.data:
            return insert_result.data[0]
        raise HTTPException(status_code=500, detail="Failed to create subscription")
