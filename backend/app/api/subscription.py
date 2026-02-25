from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.deps import DbClient, UserId
from app.middleware.rate_limit import limiter

router = APIRouter(prefix="/api/subscription", tags=["subscription"])
logger = structlog.get_logger("skolar.subscription")

from app.services.subscription_check import FREE_TIER_LIMIT  # noqa: E402  # 10 worksheets/month


class SubscriptionStatus(BaseModel):
    tier: str
    worksheets_generated_this_month: int
    worksheets_remaining: int | None  # None for unlimited (paid)
    can_generate: bool
    can_use_regional_languages: bool
    can_upload_syllabus: bool
    can_use_multi_child: bool


def ensure_subscription_exists(user_id: str, db: DbClient) -> dict:
    """Ensure user has a subscription record, create if not exists."""
    result = db.table("user_subscriptions").select("*").eq("user_id", user_id).execute()

    if result.data and len(result.data) > 0:
        sub = result.data[0]
        # Check if we need to reset monthly count
        month_reset_at = datetime.fromisoformat(sub["month_reset_at"].replace("Z", "+00:00"))
        if datetime.now(month_reset_at.tzinfo) >= month_reset_at:
            # Reset the monthly count
            new_reset = (datetime.now().replace(day=1) + timedelta(days=32)).replace(day=1)
            update_result = (
                db.table("user_subscriptions")
                .update(
                    {
                        "worksheets_generated_this_month": 0,
                        "month_reset_at": new_reset.isoformat(),
                        "updated_at": datetime.now().isoformat(),
                    }
                )
                .eq("user_id", user_id)
                .execute()
            )
            if update_result.data:
                return update_result.data[0]
        return sub
    else:
        # Create new subscription
        insert_result = (
            db.table("user_subscriptions")
            .insert(
                {
                    "user_id": user_id,
                    "tier": "free",
                    "worksheets_generated_this_month": 0,
                }
            )
            .execute()
        )
        if insert_result.data:
            return insert_result.data[0]
        raise HTTPException(status_code=500, detail="Failed to create subscription")


from datetime import timedelta  # noqa: E402


@router.get("/status", response_model=SubscriptionStatus)
@limiter.limit("60/minute")
async def get_subscription_status(request: Request, user_id: UserId, db: DbClient):
    """Get current user's subscription status."""
    sub = ensure_subscription_exists(user_id, db)

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
@limiter.limit("30/minute")
async def increment_usage(request: Request, user_id: UserId, db: DbClient):
    """Increment worksheet usage count. Called after successful generation."""
    sub = ensure_subscription_exists(user_id, db)

    # Don't track for paid users
    if sub["tier"] == "paid":
        return {"success": True, "tracked": False}

    new_count = sub["worksheets_generated_this_month"] + 1

    db.table("user_subscriptions").update(
        {"worksheets_generated_this_month": new_count, "updated_at": datetime.now().isoformat()}
    ).eq("user_id", user_id).execute()

    return {"success": True, "new_count": new_count, "remaining": max(0, FREE_TIER_LIMIT - new_count)}


@router.post("/upgrade")
@limiter.limit("10/minute")
async def upgrade_to_paid(request: Request, user_id: UserId, db: DbClient):
    """Upgrade user to paid tier. Disabled until payment integration is live."""
    # user_id dependency already validated the token
    raise HTTPException(status_code=503, detail="Payment integration coming soon")
