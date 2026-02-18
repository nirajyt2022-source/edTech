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

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel
from supabase import create_client

from app.core.config import get_settings
from app.services.report_generator import ClassReportGenerator
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)

router = APIRouter(prefix="/api", tags=["reports"])

# Shareable link base — matches the Vercel deployment
_SHARE_BASE = "https://ed-tech-drab.vercel.app"


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

class ContactItem(BaseModel):
    child_id: str
    parent_email: str


class SendEmailBody(BaseModel):
    report_token: str


# ---------------------------------------------------------------------------
# Auth helper (same pattern as classes.py / share.py)
# ---------------------------------------------------------------------------

def _get_user_id(authorization: str) -> str:
    """Extract user_id from Supabase JWT; raise 401 on failure."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.replace("Bearer ", "")
    try:
        resp = supabase.auth.get_user(token)
        if not resp or not resp.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return resp.user.id
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[reports._get_user_id] Auth failed: %s", exc)
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}")


# ---------------------------------------------------------------------------
# Endpoint 1 — generate report (teacher only)
# ---------------------------------------------------------------------------

@router.post("/teacher/classes/{class_id}/report")
async def generate_class_report(
    class_id: str,
    authorization: str = Header(None),
):
    """Generate a shareable class report and store it in class_reports."""
    teacher_id = _get_user_id(authorization)

    try:
        gen = ClassReportGenerator(supabase_client=supabase)
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

def _increment_view_count(token: str) -> None:
    """Fire-and-forget: bump view_count for a report by token."""
    try:
        r = (
            supabase.table("class_reports")
            .select("view_count")
            .eq("token", token)
            .maybe_single()
            .execute()
        )
        row = getattr(r, "data", None)
        if row:
            new_count = (row.get("view_count") or 0) + 1
            (
                supabase.table("class_reports")
                .update({"view_count": new_count})
                .eq("token", token)
                .execute()
            )
    except Exception as exc:
        logger.warning("[reports._increment_view_count] Failed for token %.12s…: %s", token, exc)


@router.get("/reports/{token}")
async def get_report_by_token(
    token: str,
    background_tasks: BackgroundTasks,
):
    """Public endpoint. Returns report_data JSONB for a valid, non-expired token."""
    try:
        r = (
            supabase.table("class_reports")
            .select("report_data, expires_at, view_count")
            .eq("token", token)
            .maybe_single()
            .execute()
        )
        row = getattr(r, "data", None)
    except Exception as exc:
        logger.error("[reports.get_report_by_token] DB error for token %.12s…: %s", token, exc)
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
            logger.warning("[reports.get_report_by_token] Cannot parse expires_at %r: %s", expires_str, exc)

    # Increment view count in the background (fire and forget)
    background_tasks.add_task(_increment_view_count, token)

    return row["report_data"]


# ---------------------------------------------------------------------------
# Endpoint 3 — list parent contacts (teacher only)
# ---------------------------------------------------------------------------

@router.get("/teacher/classes/{class_id}/contacts")
async def get_class_contacts(
    class_id: str,
    authorization: str = Header(None),
):
    """Return [{child_id, child_name, parent_email}] for a class."""
    teacher_id = _get_user_id(authorization)
    _verify_class_ownership(class_id, teacher_id)

    try:
        r = (
            supabase.table("class_contacts")
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
            "child_name": (
                row["children"]["name"]
                if isinstance(row.get("children"), dict)
                else ""
            ),
            "parent_email": row.get("parent_email") or "",
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Endpoint 4 — upsert parent contacts (teacher only)
# ---------------------------------------------------------------------------

@router.post("/teacher/classes/{class_id}/contacts")
async def upsert_class_contacts(
    class_id: str,
    body: List[ContactItem],
    authorization: str = Header(None),
):
    """Upsert parent email contacts for a class."""
    teacher_id = _get_user_id(authorization)
    _verify_class_ownership(class_id, teacher_id)

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
        supabase.table("class_contacts").upsert(
            rows, on_conflict="class_id,child_id"
        ).execute()
    except Exception as exc:
        logger.error("[reports.upsert_class_contacts] DB error for class %s: %s", class_id, exc)
        raise HTTPException(status_code=500, detail="Failed to save contacts")

    return {"updated": len(rows)}


# ---------------------------------------------------------------------------
# Endpoint 5 — send email report (teacher only)
# ---------------------------------------------------------------------------

@router.post("/teacher/classes/{class_id}/report/send-email")
async def send_email_report(
    class_id: str,
    body: SendEmailBody,
    authorization: str = Header(None),
):
    """Send personalised report emails to parents via Resend."""
    teacher_id = _get_user_id(authorization)
    _verify_class_ownership(class_id, teacher_id)

    # Resolve teacher display name from JWT metadata
    teacher_name = ""
    try:
        token_str = authorization.replace("Bearer ", "")
        user_resp = supabase.auth.get_user(token_str)
        if user_resp and user_resp.user:
            teacher_name = (user_resp.user.user_metadata or {}).get("name", "")
    except Exception as exc:
        logger.warning("[reports.send_email_report] Could not resolve teacher name: %s", exc)

    # Fetch report
    try:
        r = (
            supabase.table("class_reports")
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
        contacts_r = (
            supabase.table("class_contacts")
            .select("child_id, parent_email")
            .eq("class_id", class_id)
            .execute()
        )
        contact_rows = getattr(contacts_r, "data", None) or []
    except Exception as exc:
        logger.error("[reports.send_email_report] DB error fetching contacts: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch contacts")

    parent_emails = {
        row["child_id"]: row["parent_email"]
        for row in contact_rows
        if row.get("parent_email")
    }

    if not parent_emails:
        return {"sent": 0, "skipped": len(report_data.get("children", [])),
                "error": "No parent emails configured for this class."}

    svc = EmailService(
        api_key=settings.resend_api_key,
        from_email=settings.resend_from_email,
    )
    result = await svc.send_class_report(report_data, parent_emails, teacher_name)
    return result


# ---------------------------------------------------------------------------
# Shared helper — verify class ownership (raises 403 on failure)
# ---------------------------------------------------------------------------

def _verify_class_ownership(class_id: str, teacher_id: str) -> None:
    """Raise HTTPException 403 if teacher doesn't own the class."""
    try:
        r = (
            supabase.table("teacher_classes")
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
