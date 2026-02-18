"""EmailService — sends per-child report emails to parents via Resend.

Rules:
  - No LLM calls.  HTML is built with pure string templates.
  - Requires RESEND_API_KEY env var; gracefully skips if missing.
  - send_class_report is async; wraps the synchronous resend SDK with
    asyncio.to_thread so the FastAPI event loop is never blocked.
  - One email per child/parent pair; skips children with no email on record.
"""
from __future__ import annotations

import asyncio
import logging
from html import escape

logger = logging.getLogger(__name__)

# ── Share-link base (matches the Vercel deployment) ───────────────────────────
_SHARE_BASE = "https://ed-tech-drab.vercel.app"

# ── Colours (same palette as ClassReport.tsx) ─────────────────────────────────
_GREEN  = "#2d6a4f"
_AMBER  = "#b45309"
_BG     = "#f5f4f0"
_CARD   = "#ffffff"
_MUTED  = "#6b7280"
_BODY   = "#374151"
_BORDER = "#e5e7eb"


class EmailService:
    """Sends personalised report emails to parents using Resend."""

    def __init__(self, api_key: str, from_email: str = "onboarding@resend.dev"):
        self._api_key = api_key or ""
        self._from_email = from_email

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    async def send_class_report(
        self,
        report: dict,
        parent_emails: dict[str, str],
        teacher_name: str = "",
    ) -> dict:
        """Send one personalised email per child who has a parent email on record.

        Args:
            report:        The full report_data dict from class_reports.
            parent_emails: {child_id: parent_email_address}
            teacher_name:  Display name of the teacher (shown in email header).

        Returns:
            {"sent": N, "skipped": M}
        """
        if not self._api_key:
            logger.warning(
                "[EmailService] RESEND_API_KEY not configured — skipping email send"
            )
            return {
                "sent": 0,
                "skipped": len(report.get("children", [])),
                "error": "Email delivery is not configured (RESEND_API_KEY missing).",
            }

        sent = 0
        skipped = 0

        for child in report.get("children", []):
            child_id = child.get("child_id")
            email = (parent_emails.get(child_id) or "").strip()
            if not email:
                skipped += 1
                continue

            subject = f"Weekly Learning Report — {child['name']}"
            html = self._build_email_html(report, child, teacher_name)

            try:
                await asyncio.to_thread(self._send_one, email, subject, html)
                sent += 1
                logger.info(
                    "[EmailService] Sent report for child %r to %s",
                    child.get("name"), email,
                )
            except Exception as exc:
                logger.error(
                    "[EmailService] Failed to send to %s for child %r: %s",
                    email, child.get("name"), exc,
                )
                skipped += 1

        return {"sent": sent, "skipped": skipped}

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _send_one(self, to_email: str, subject: str, html: str) -> None:
        """Synchronous resend API call — run via asyncio.to_thread."""
        import resend  # imported here so tests that skip email don't need resend installed
        resend.api_key = self._api_key
        resend.Emails.send({
            "from": self._from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        })

    def _build_email_html(
        self,
        report: dict,
        child: dict,
        teacher_name: str,
    ) -> str:
        """Build a Gmail-safe HTML email for one child's weekly report."""

        token       = report.get("expires_at", "")  # used for link; actually we need token
        class_name  = escape(report.get("class_name", "Your Class"))
        subject_str = escape(report.get("subject", ""))
        grade       = escape(str(report.get("grade", "")))
        report_url  = escape(report.get("_report_url", ""))  # injected by the endpoint

        child_name  = escape(child.get("name", "Your child"))
        report_text = escape(child.get("report_text", ""))
        mastered    = int(child.get("mastered_count", 0))
        needs_attn  = int(child.get("needs_attention_count", 0))
        rec         = child.get("recommendation", "")

        teacher_label = escape(teacher_name) if teacher_name else "Your Teacher"

        # ── Meta line ─────────────────────────────────────────────────────────
        meta_parts = [class_name]
        if subject_str:
            meta_parts.append(subject_str)
        if grade:
            meta_parts.append(f"Class {grade}")
        meta_line = escape(" · ".join(meta_parts))

        # ── Mastered badge ────────────────────────────────────────────────────
        mastered_badge = (
            f'<span style="display:inline-block;padding:4px 12px;'
            f'background:#d1fae5;color:#065f46;border-radius:20px;'
            f'font-size:13px;font-weight:700;margin-right:8px;">'
            f'&#9679; {mastered} Mastered</span>'
        )

        # ── Needs-practice badge (only if >0) ─────────────────────────────────
        needs_badge = ""
        if needs_attn > 0:
            needs_badge = (
                f'<span style="display:inline-block;padding:4px 12px;'
                f'background:#fef3c7;color:#92400e;border-radius:20px;'
                f'font-size:13px;font-weight:700;">'
                f'&#9679; {needs_attn} Need Practice</span>'
            )

        # ── Recommendation block (only if present) ────────────────────────────
        rec_block = ""
        if rec:
            rec_display = escape(rec.replace("Practice next: ", "").rstrip("."))
            rec_block = (
                f'<div style="margin-top:16px;padding:12px 16px;'
                f'background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;">'
                f'<p style="margin:0 0 4px;font-size:10px;font-weight:700;'
                f'color:#15803d;text-transform:uppercase;letter-spacing:0.05em;">This week</p>'
                f'<p style="margin:0;font-size:13px;color:#166534;line-height:1.5;">{rec_display}</p>'
                f'</div>'
            )

        # ── CTA button ────────────────────────────────────────────────────────
        cta = (
            f'<div style="margin-top:24px;">'
            f'<a href="{report_url}" '
            f'style="display:inline-block;padding:12px 28px;background:{_GREEN};'
            f'color:#ffffff;text-decoration:none;border-radius:8px;'
            f'font-size:14px;font-weight:700;font-family:Arial,sans-serif;">'
            f'View Full Report &rarr;</a>'
            f'</div>'
        ) if report_url else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{_BG};font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:{_BG};padding:24px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;background:{_CARD};
                      border-radius:12px;overflow:hidden;
                      border:1px solid {_BORDER};">

          <!-- ── Header ── -->
          <tr>
            <td style="background:{_GREEN};padding:24px 32px;">
              <p style="margin:0 0 2px;color:#d8f3dc;font-size:11px;
                        font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">
                PracticeCraft</p>
              <h1 style="margin:0 0 6px;color:#ffffff;font-size:20px;font-weight:700;">
                Weekly Learning Report</h1>
              <p style="margin:0;color:#a7f3d0;font-size:13px;">
                {meta_line} &nbsp;&bull;&nbsp; From: {teacher_label}</p>
            </td>
          </tr>

          <!-- ── Child section ── -->
          <tr>
            <td style="padding:28px 32px;">
              <h3 style="margin:0 0 14px;color:#1a2e1a;font-size:18px;font-weight:700;">
                {child_name}</h3>
              <p style="margin:0 0 20px;color:{_BODY};font-size:16px;line-height:1.65;">
                {report_text}</p>

              <!-- Badges -->
              <div style="margin-bottom:4px;">
                {mastered_badge}{needs_badge}
              </div>

              {rec_block}
              {cta}
            </td>
          </tr>

          <!-- ── Footer ── -->
          <tr>
            <td style="padding:16px 32px;border-top:1px solid {_BORDER};
                       background:#fafaf8;">
              <p style="margin:0;color:{_MUTED};font-size:12px;text-align:center;">
                Powered by <strong style="color:#4b5563;">PracticeCraft</strong>
                &mdash; CBSE Learning for Classes 1&ndash;5
              </p>
              <p style="margin:6px 0 0;color:#9ca3af;font-size:11px;text-align:center;">
                Valid for 7 days &bull; You received this because your child's teacher
                shared a class report.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
