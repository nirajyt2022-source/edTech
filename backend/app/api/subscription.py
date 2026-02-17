from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from datetime import datetime
from supabase import create_client
from app.core.config import get_settings

router = APIRouter(prefix="/api/subscription", tags=["subscription"])

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)

from app.services.subscription_check import FREE_TIER_LIMIT  # 10 worksheets/month


class SubscriptionStatus(BaseModel):
    tier: str
    worksheets_generated_this_month: int
    worksheets_remaining: int | None  # None for unlimited (paid)
    can_generate: bool
    can_use_regional_languages: bool
    can_upload_syllabus: bool
    can_use_multi_child: bool


def get_user_id_from_token(authorization: str) -> str:
    """Extract user_id from Supabase JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_response.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


def ensure_subscription_exists(user_id: str) -> dict:
    """Ensure user has a subscription record, create if not exists."""
    result = supabase.table("user_subscriptions") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if result.data and len(result.data) > 0:
        sub = result.data[0]
        # Check if we need to reset monthly count
        month_reset_at = datetime.fromisoformat(sub["month_reset_at"].replace("Z", "+00:00"))
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


from datetime import timedelta


@router.get("/status", response_model=SubscriptionStatus)
async def get_subscription_status(authorization: str = Header(None)):
    """Get current user's subscription status."""
    user_id = get_user_id_from_token(authorization)
    sub = ensure_subscription_exists(user_id)

    is_paid = sub["tier"] == "paid"
    worksheets_used = sub["worksheets_generated_this_month"]

    if is_paid:
        worksheets_remaining = None
        can_generate = True
    else:
        worksheets_remaining = max(0, FREE_TIER_LIMIT - worksheets_used)
        can_generate = worksheets_remaining > 0

    return SubscriptionStatus(
        tier=sub["tier"],
        worksheets_generated_this_month=worksheets_used,
        worksheets_remaining=worksheets_remaining,
        can_generate=can_generate,
        can_use_regional_languages=is_paid,
        can_upload_syllabus=is_paid,
        can_use_multi_child=is_paid,
    )


@router.post("/increment-usage")
async def increment_usage(authorization: str = Header(None)):
    """Increment worksheet usage count. Called after successful generation."""
    user_id = get_user_id_from_token(authorization)
    sub = ensure_subscription_exists(user_id)

    # Don't track for paid users
    if sub["tier"] == "paid":
        return {"success": True, "tracked": False}

    new_count = sub["worksheets_generated_this_month"] + 1

    supabase.table("user_subscriptions") \
        .update({
            "worksheets_generated_this_month": new_count,
            "updated_at": datetime.now().isoformat()
        }) \
        .eq("user_id", user_id) \
        .execute()

    return {"success": True, "new_count": new_count, "remaining": max(0, FREE_TIER_LIMIT - new_count)}


@router.post("/upgrade")
async def upgrade_to_paid(authorization: str = Header(None)):
    """Upgrade user to paid tier. (Placeholder - integrate with payment provider)"""
    user_id = get_user_id_from_token(authorization)

    # TODO: Integrate with Stripe/Razorpay for actual payment
    # For now, this is a placeholder that upgrades immediately

    result = supabase.table("user_subscriptions") \
        .update({
            "tier": "paid",
            "updated_at": datetime.now().isoformat()
        }) \
        .eq("user_id", user_id) \
        .execute()

    if result.data:
        return {"success": True, "tier": "paid"}
    raise HTTPException(status_code=500, detail="Failed to upgrade")
