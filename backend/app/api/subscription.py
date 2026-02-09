from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from datetime import datetime
from supabase import create_client
from app.core.config import get_settings
from app.services.subscription import ensure_subscription_exists, FREE_TIER_LIMIT

router = APIRouter(prefix="/api/subscription", tags=["subscription"])

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)


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


# Function ensure_subscription_exists moved to app.services.subscription

from datetime import timedelta


@router.get("/status", response_model=SubscriptionStatus)
async def get_subscription_status(authorization: str = Header(None)):
    """Get current user's subscription status."""
    user_id = get_user_id_from_token(authorization)
    sub = ensure_subscription_exists(supabase, user_id)

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
    sub = ensure_subscription_exists(supabase, user_id)

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
async def upgrade_to_paid(
    authorization: str = Header(None),
    admin_secret: str | None = Header(None)
):
    """Upgrade user to paid tier. (Placeholder - integrate with payment provider)"""
    user_id = get_user_id_from_token(authorization)

    # SECURE: In production, this should only be called by a webhook from a payment provider
    # or after verifying a payment receipt.
    # For development/testing, we allow it with the admin secret.
    if settings.debug is False and (not admin_secret or admin_secret != settings.admin_secret):
        raise HTTPException(
            status_code=403,
            detail="Payment integration required for public upgrades."
        )

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
