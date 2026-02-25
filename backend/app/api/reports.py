"""Reports API.

POST /api/teacher/classes/{class_id}/report
    Authenticated (teacher). Generates and stores a class report.
    Returns { token, share_url, expires_at }.

GET /api/reports/{token}
    Public (no auth). Returns report_data JSONB.
    404 – not found.  410 – expired.  Increments view_count (fire & forget).

GET  /api/teacher/classes/{class_id}/contacts
    Authenticated (teacher). Returns [{child_id, child_name, parent_email}].

POST /api/teacher/classes/{class_id}/contacts
    Authenticated (teacher). Upserts parent email contacts.
    Body: [{child_id, parent_email}]

POST /api/teacher/classes/{class_id}/report/send-email
    Authenticated (teacher). Sends report emails to parents via Resend.
    Body: {report_token}
    Returns {sent, skipped}.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import structlog
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.deps import DbClient, UserId
from app.middleware.rate_limit import limiter
from app.services.email_service import EmailService
from app.services.report_generator import ClassReportGenerator

logger = structlog.get_logger("skolar.reports")

router = APIRouter(prefix="/api", tags=["reports"])

_SHARE_BASE = get_settings().frontend_url


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------


class ContactItem(BaseModel):
    child_id: str
    parent_email: str


class SendEmailBody(BaseModel):
    report_token: str


# ---------------------------------------------------------------------------
# Endpoint 1 — generate report (teacher only)
# ---------------------------------------------------------------------------


@router.post("/teacher/classes/{class_id}/report")
@limiter.limit("10/minute")
async def generate_class_report(
    request: Request,
    class_id: str,
    teacher_id: UserId,
    db: DbClient,
):
    """Generate a shareable class report and store it in class_reports."""
    try:
        gen = ClassReportGenerator(supabase_client=db)
        result = gen.generate_class_report(class_id, teacher_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RuntimeError as exc:
        logger.error("[reports.generate_class_report] Failed for class %s: %s", class_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.error("[reports.generate_class_report] Unexpected error for class %s: %s", class_id, exc)
        raise HTTPException(status_code=500, detail="Report generation failed")

    token = result["token"]
    return {
        "token": token,
        "share_url": f"{_SHARE_BASE}/reports/{token}",
        "expires_at": result["expires_at"],
    }


# ---------------------------------------------------------------------------
# Endpoint 2 — public viewer (no auth)
# ---------------------------------------------------------------------------


def _increment_view_count(db: DbClient, token: str) -> None:
    """Fire-and-forget: bump view_count for a report by token."""
    try:
        r = db.table("class_reports").select("view_count").eq("token", token).maybe_single().execute()
        row = getattr(r, "data", None)
        if row:
            new_count = (row.get("view_count") or 0) + 1
            (db.table("class_reports").update({"view_count": new_count}).eq("token", token).execute())
    except Exception as exc:
        logger.warning("[reports._increment_view_count] Failed for report_id %.12s…: %s", token, exc)


@router.get("/reports/{token}")
@limiter.limit("60/minute")
async def get_report_by_token(
    request: Request,
    token: str,
    background_tasks: BackgroundTasks,
    db: DbClient,
):
    """Public endpoint. Returns report_data JSONB for a valid, non-expired token."""
    try:
        r = (
            db.table("class_reports")
            .select("report_data, expires_at, view_count")
            .eq("token", token)
            .maybe_single()
            .execute()
        )
        row = getattr(r, "data", None)
    except Exception as exc:
        logger.error("[reports.get_public_report] DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch report")

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    # Expiry check
    expires_str: str | None = row.get("expires_at")
    if expires_str:
        try:
            expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                raise HTTPException(status_code=410, detail="Report has expired")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("[reports.get_report] Cannot parse expires_at %r: %s", expires_str, exc)

    # Increment view count in the background (fire and forget)
    background_tasks.add_task(_increment_view_count, db, token)

    return row["report_data"]


# ---------------------------------------------------------------------------
# Endpoint 3 — list parent contacts (teacher only)
# ---------------------------------------------------------------------------


@router.get("/teacher/classes/{class_id}/contacts")
@limiter.limit("60/minute")
async def get_class_contacts(
    request: Request,
    class_id: str,
    teacher_id: UserId,
    db: DbClient,
):
    """Return [{child_id, child_name, parent_email}] for a class."""
    _verify_class_ownership(db, class_id, teacher_id)

    try:
        r = (
            db.table("class_contacts")
            .select("child_id, parent_email, children(name)")
            .eq("class_id", class_id)
            .execute()
        )
        rows = getattr(r, "data", None) or []
    except Exception as exc:
        logger.error("[reports.get_class_contacts] DB error for class %s: %s", class_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch contacts")

    return [
        {
            "child_id": row["child_id"],
            "child_name": (row["children"]["name"] if isinstance(row.get("children"), dict) else ""),
            "parent_email": row.get("parent_email") or "",
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Endpoint 4 — upsert parent contacts (teacher only)
# ---------------------------------------------------------------------------


@router.post("/teacher/classes/{class_id}/contacts")
@limiter.limit("30/minute")
async def upsert_class_contacts(
    request: Request,
    class_id: str,
    body: List[ContactItem],
    teacher_id: UserId,
    db: DbClient,
):
    """Upsert parent email contacts for a class."""
    _verify_class_ownership(db, class_id, teacher_id)

    rows = [
        {
            "class_id": class_id,
            "child_id": item.child_id,
            "parent_email": item.parent_email.strip(),
        }
        for item in body
        if item.parent_email and item.parent_email.strip()
    ]

    if not rows:
        return {"updated": 0}

    try:
        db.table("class_contacts").upsert(rows, on_conflict="class_id,child_id").execute()
    except Exception as exc:
        logger.error("[reports.upsert_class_contacts] DB error for class %s: %s", class_id, exc)
        raise HTTPException(status_code=500, detail="Failed to save contacts")

    return {"updated": len(rows)}


# ---------------------------------------------------------------------------
# Endpoint 5 — send email report (teacher only)
# ---------------------------------------------------------------------------


@router.post("/teacher/classes/{class_id}/report/send-email")
@limiter.limit("5/minute")
async def send_email_report(
    request: Request,
    class_id: str,
    body: SendEmailBody,
    teacher_id: UserId,
    db: DbClient,
    authorization: str = Header(...),
):
    """Send personalised report emails to parents via Resend."""
    _verify_class_ownership(db, class_id, teacher_id)

    # Resolve teacher display name from JWT metadata
    teacher_name = ""
    try:
        token_str = authorization.replace("Bearer ", "")
        user_resp = db.auth.get_user(token_str)
        if user_resp and user_resp.user:
            teacher_name = (user_resp.user.user_metadata or {}).get("name", "")
    except Exception as exc:
        logger.warning("[reports.send_email_report] Could not resolve teacher name: %s", exc)

    # Fetch report
    try:
        r = (
            db.table("class_reports")
            .select("report_data, expires_at, token")
            .eq("token", body.report_token)
            .maybe_single()
            .execute()
        )
        row = getattr(r, "data", None)
    except Exception as exc:
        logger.error("[reports.send_email_report] DB error fetching report: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch report")

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    report_data: dict = row["report_data"]
    # Inject the shareable URL so the email template can build the CTA button
    report_data["_report_url"] = f"{_SHARE_BASE}/report/{body.report_token}"

    # Fetch parent contacts for this class
    try:
        contacts_r = db.table("class_contacts").select("child_id, parent_email").eq("class_id", class_id).execute()
        contact_rows = getattr(contacts_r, "data", None) or []
    except Exception as exc:
        logger.error("[reports.send_email_report] DB error fetching contacts: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch contacts")

    parent_emails = {row["child_id"]: row["parent_email"] for row in contact_rows if row.get("parent_email")}

    if not parent_emails:
        return {
            "sent": 0,
            "skipped": len(report_data.get("children", [])),
            "error": "No parent emails configured for this class.",
        }

    _settings = get_settings()
    svc = EmailService(
        api_key=_settings.resend_api_key,
        from_email=_settings.resend_from_email,
    )
    result = await svc.send_class_report(report_data, parent_emails, teacher_name)
    return result


# ---------------------------------------------------------------------------
# Shared helper — verify class ownership (raises 403 on failure)
# ---------------------------------------------------------------------------


def _verify_class_ownership(db: DbClient, class_id: str, teacher_id: str) -> None:
    """Raise HTTPException 403 if teacher doesn't own the class."""
    try:
        r = (
            db.table("teacher_classes")
            .select("id")
            .eq("id", class_id)
            .eq("user_id", teacher_id)
            .maybe_single()
            .execute()
        )
        if not getattr(r, "data", None):
            raise HTTPException(status_code=403, detail="Class not found or access denied")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[reports._verify_class_ownership] DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to verify class ownership")
