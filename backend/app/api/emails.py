"""Email sequence API — webhook endpoints for welcome drip emails.

Endpoints:
  POST /api/emails/webhook/signup      — triggers Email 1 on new signup
  POST /api/emails/process-sequence    — processes pending emails (called by cron)

Both are protected by X-Webhook-Secret header (not user JWT).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.deps import DbClient
from app.services.welcome_emails import process_pending_emails, send_welcome_email_1

router = APIRouter(prefix="/api/emails", tags=["emails"])
logger = structlog.get_logger("skolar.emails")


def _verify_webhook_secret(request: Request) -> None:
    """Raise 401 if X-Webhook-Secret header doesn't match config."""
    settings = get_settings()
    if not settings.email_webhook_secret:
        raise HTTPException(status_code=500, detail="EMAIL_WEBHOOK_SECRET not configured")
    secret = request.headers.get("X-Webhook-Secret", "")
    if secret != settings.email_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


class SignupWebhookBody(BaseModel):
    user_id: str
    email: str


@router.post("/webhook/signup")
async def webhook_signup(body: SignupWebhookBody, request: Request, db: DbClient):
    """Handle new user signup — send Email 1 and start sequence."""
    _verify_webhook_secret(request)

    user_id = body.user_id
    email = body.email

    # Fetch child + profile info for personalisation
    parent_name = ""
    child_name = ""
    grade = ""

    try:
        profile = db.table("profiles").select("full_name").eq("id", user_id).maybe_single().execute()
        if profile.data:
            parent_name = profile.data.get("full_name", "") or ""
    except Exception:
        logger.warning("Could not fetch profile for user %s", user_id)

    try:
        child = db.table("children").select("name, grade").eq("user_id", user_id).limit(1).execute()
        if child.data:
            child_name = child.data[0].get("name", "") or ""
            grade = child.data[0].get("grade", "") or ""
    except Exception:
        logger.warning("Could not fetch children for user %s", user_id)

    # Check idempotency — don't restart an existing sequence
    existing = db.table("email_sequence").select("user_id").eq("user_id", user_id).maybe_single().execute()
    if existing.data:
        logger.info("Email sequence already exists for user %s — skipping", user_id)
        return {"success": True, "email_sent": 0, "note": "sequence already exists"}

    await send_welcome_email_1(db, user_id, email, parent_name, child_name, grade)

    return {"success": True, "email_sent": 1}


@router.post("/process-sequence")
async def process_sequence(request: Request, db: DbClient):
    """Process all pending emails in the welcome sequence. Called by cron."""
    _verify_webhook_secret(request)

    result = await process_pending_emails(db)

    logger.info(
        "Email sequence processed",
        processed=result["processed"],
        sent=result["sent"],
        skipped=result["skipped"],
    )

    return result
