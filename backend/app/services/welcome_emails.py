"""Welcome email sequence — 5 drip emails over 7 days after signup.

Sends via Resend (same pattern as email_service.py). All HTML is inline,
mobile-first, 600px max, system fonts.

Public API:
  - send_welcome_email_1(db, user_id, email, parent_name, child_name, grade)
  - process_pending_emails(db) → {"processed": N, "sent": M, "skipped": K}
"""

from __future__ import annotations

import asyncio
import logging
from html import escape

logger = logging.getLogger(__name__)

# ── Brand colours ────────────────────────────────────────────────────────────
_GREEN = "#2d6a4f"
_BG = "#f5f4f0"
_CARD = "#ffffff"
_MUTED = "#6b7280"
_BODY = "#374151"
_BORDER = "#e5e7eb"

# ── Timing between emails (hours) ───────────────────────────────────────────
_DELAYS_HOURS = {
    1: 24,  # after Email 1 → send Email 2 in 24h
    2: 48,  # after Email 2 → send Email 3 in 48h
    3: 48,  # after Email 3 → send Email 4 in 48h
    4: 48,  # after Email 4 → send Email 5 in 48h
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_app_url() -> str:
    from app.core.config import get_settings

    return get_settings().frontend_url.rstrip("/")


def _get_resend_config() -> tuple[str, str]:
    """Return (api_key, from_email)."""
    from app.core.config import get_settings

    s = get_settings()
    return s.resend_api_key, s.resend_from_email


def _send_email_sync(to: str, subject: str, html: str) -> None:
    """Synchronous resend send — run via asyncio.to_thread."""
    import resend

    api_key, from_email = _get_resend_config()
    if not api_key:
        logger.warning("[WelcomeEmails] Email delivery not configured — skipping send to %s", to)
        return

    resend.api_key = api_key
    resend.Emails.send(
        {
            "from": from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        }
    )


async def _send_email(to: str, subject: str, html: str) -> None:
    await asyncio.to_thread(_send_email_sync, to, subject, html)


# ── Email wrapper (shared header/footer) ────────────────────────────────────


def _wrap_email(header_title: str, body_html: str, footer_note: str = "") -> str:
    """Wrap body content in the branded email shell."""
    footer_extra = ""
    if footer_note:
        footer_extra = f'<p style="margin:6px 0 0;color:#9ca3af;font-size:11px;text-align:center;">{footer_note}</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{_BG};font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_BG};padding:24px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px;width:100%;background:{_CARD};border-radius:12px;overflow:hidden;border:1px solid {_BORDER};">
        <tr><td style="background:{_GREEN};padding:24px 32px;">
          <p style="margin:0 0 2px;color:#d8f3dc;font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">Skolar</p>
          <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:700;">{header_title}</h1>
        </td></tr>
        <tr><td style="padding:28px 32px;color:{_BODY};font-size:15px;line-height:1.65;">
          {body_html}
        </td></tr>
        <tr><td style="padding:16px 32px;border-top:1px solid {_BORDER};background:#fafaf8;">
          <p style="margin:0;color:{_MUTED};font-size:12px;text-align:center;">
            Powered by <strong style="color:#4b5563;">Skolar</strong> &mdash; CBSE worksheets for Class 1&ndash;5
          </p>
          {footer_extra}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _cta_button(text: str, url: str) -> str:
    return (
        f'<div style="margin:24px 0 8px;">'
        f'<a href="{url}" style="display:inline-block;padding:14px 28px;background:{_GREEN};'
        f"color:#ffffff;text-decoration:none;border-radius:8px;font-size:14px;font-weight:700;"
        f'font-family:Arial,sans-serif;">{text}</a></div>'
    )


# ── Email templates ──────────────────────────────────────────────────────────


def _build_email_1(parent_name: str, child_name: str, grade: str) -> tuple[str, str]:
    """Welcome email — immediate on signup."""
    app = _get_app_url()
    p = escape(parent_name or "there")
    c = escape(child_name or "your child")
    g = escape(grade or "")

    subject = f"Welcome to Skolar, {p}!"
    body = f"""
<p style="margin:0 0 16px;">Hi {p},</p>
<p style="margin:0 0 16px;">Welcome to Skolar! You just took a great step for {c}'s learning.
Ab practice ke liye sahi worksheets dhundhne ka jhanjhat khatam.</p>
<p style="margin:0 0 8px;">Here's what you get &mdash; bilkul free:</p>
<ul style="margin:0 0 16px;padding-left:20px;">
  <li>5 worksheets every month</li>
  <li>All 9 CBSE subjects (Class {g})</li>
  <li>PDF with answer key included</li>
  <li>Every maths answer verified by code &mdash; no wrong answers</li>
</ul>
<p style="margin:0 0 16px;">Your first worksheet takes 30 seconds. Pick a subject, pick a topic,
and Skolar does the rest.</p>
{_cta_button(f"Generate {c}'s first worksheet &rarr;", f"{app}/generator?grade={g}")}
<p style="margin:16px 0 0;font-size:13px;color:{_MUTED};">
3 difficulty levels. 5 types of questions per sheet.
Made for the exact CBSE syllabus {c} follows in school.</p>
<p style="margin:16px 0 0;">Koi bhi doubt ho toh simply reply karein &mdash; I read every email.</p>
<p style="margin:16px 0 0;">&mdash; Team Skolar</p>
<p style="margin:8px 0 0;font-size:13px;color:{_MUTED};">P.S. Most parents start with Maths or Hindi. Just saying.</p>
"""
    return subject, _wrap_email("Welcome to Skolar!", body)


def _build_email_2(parent_name: str, child_name: str, grade: str) -> tuple[str, str]:
    """Day 1 nudge — only if no worksheets generated."""
    app = _get_app_url()
    p = escape(parent_name or "there")
    c = escape(child_name or "your child")
    g = escape(grade or "")

    subject = f"{c} ka worksheet abhi ready ho sakta hai"
    body = f"""
<p style="margin:0 0 16px;">Hi {p},</p>
<p style="margin:0 0 16px;">Kal aapne Skolar join kiya &mdash; great! But {c} ka first worksheet abhi baki hai.</p>
<p style="margin:0 0 8px;">Koi baat nahi, it literally takes 30 seconds:</p>
<ol style="margin:0 0 16px;padding-left:20px;">
  <li>Pick a subject (Maths, English, Hindi&hellip;)</li>
  <li>Choose the topic (Addition, Nouns, Varnamala&hellip;)</li>
  <li>Click &ldquo;Generate&rdquo; &mdash; done!</li>
</ol>
<p style="margin:0 0 16px;">You'll get a PDF with the worksheet AND the answer key.
Print it, or let {c} solve it on screen.</p>
{_cta_button("Generate first worksheet &rarr;", f"{app}/generator?grade={g}&subject=Maths")}
<p style="margin:16px 0 0;">Aur haan &mdash; answer key mein galti nahi hogi. Every maths answer is
checked by code, not guessed by AI. That's the Skolar promise.</p>
<p style="margin:16px 0 0;">Ek baar try karein &mdash; most parents are surprised how good it is.</p>
<p style="margin:16px 0 0;">&mdash; Team Skolar</p>
"""
    return subject, _wrap_email("Your First Worksheet Awaits", body)


def _build_email_3(
    parent_name: str,
    child_name: str,
    grade: str,
    worksheets_generated: int,
) -> tuple[str, str]:
    """Day 3 — trust & value (verified answers)."""
    app = _get_app_url()
    p = escape(parent_name or "there")
    g = escape(grade or "")

    subject = "Why Skolar answers are never wrong"

    progress_block = ""
    if worksheets_generated > 0:
        progress_block = (
            f"<p style='margin:0 0 16px;'>You've already generated {worksheets_generated} "
            f"worksheet(s). Keep going &mdash; consistency matters more than quantity.</p>"
        )
    else:
        progress_block = "<p style='margin:0 0 16px;'>You haven't tried it yet. Ek baar generate karke dekhiye:</p>"

    body = f"""
<p style="margin:0 0 16px;">Hi {p},</p>
<p style="margin:0 0 16px;">Ek problem jo har parent face karta hai:</p>
<p style="margin:0 0 16px;">You download a &ldquo;free worksheet&rdquo; from Google. Your child solves it.
You check the answer key &mdash; and the answers are WRONG.</p>
<p style="margin:0 0 8px;">Sound familiar? Skolar mein aisa nahi hoga. Here's why:</p>
<ul style="margin:0 0 16px;padding-left:20px;">
  <li><strong>MATHS:</strong> Every answer is verified by code. 2+3=5? The computer checks it.</li>
  <li><strong>ENGLISH:</strong> Grammar rules are cross-checked. Each question follows NCERT patterns for Class {g}.</li>
  <li><strong>HINDI:</strong> Devanagari worksheets with proper formatting &mdash; varnamala, matra, shabd.</li>
</ul>
<p style="margin:0 0 16px;">Plus, every worksheet has 5 types of questions:
Pehchaano (recognition), Apply karo (application), Dikhao (representation),
Galti dhoondo (error detection), Socho (thinking).</p>
<p style="margin:0 0 16px;">This isn't just practice &mdash; it builds real understanding.</p>
{progress_block}
{_cta_button("Generate a worksheet &rarr;", f"{app}/generator?grade={g}")}
<p style="margin:16px 0 0;">&mdash; Team Skolar</p>
"""
    return subject, _wrap_email("Verified Answers. Always.", body)


def _build_email_4(
    parent_name: str,
    child_name: str,
    grade: str,
    worksheets_generated: int,
) -> tuple[str, str]:
    """Day 5 — social proof."""
    app = _get_app_url()
    p = escape(parent_name or "there")
    g = escape(grade or "")

    # Grade-dependent popular topics
    if g in ("1", "2"):
        fav_topics = (
            "<li>Maths: Addition, Subtraction, Shapes</li>"
            "<li>English: Nouns, Rhyming Words</li>"
            "<li>Hindi: Varnamala, Matra</li>"
        )
    else:
        fav_topics = (
            "<li>Maths: Multiplication, Fractions, Geometry</li>"
            "<li>English: Tenses, Comprehension</li>"
            "<li>Science: Living Things, Food &amp; Nutrition</li>"
        )

    progress_note = ""
    if worksheets_generated >= 3:
        progress_note = f"<p style='margin:0 0 16px;'>Aapne abhi tak {worksheets_generated} worksheet(s) generate kiye hain. Bahut accha!</p>"
    else:
        progress_note = (
            f"<p style='margin:0 0 16px;'>Aapne abhi tak {worksheets_generated} worksheet(s) generate kiye hain. "
            "Thoda aur practice? Consistency se confidence aata hai.</p>"
        )

    subject = f"What Class {g} parents are practicing this week"
    body = f"""
<p style="margin:0 0 16px;">Hi {p},</p>
<p style="margin:0 0 16px;">Quick update &mdash; here's what other Class {g} parents on Skolar are practicing this week:</p>
<p style="margin:0 0 8px;">Class {g} parents ke favorite topics:</p>
<ul style="margin:0 0 16px;padding-left:20px;">{fav_topics}</ul>
{progress_note}
<p style="margin:0 0 16px;">Want to try a different subject?</p>
{_cta_button("Explore all 9 subjects &rarr;", f"{app}/generator?grade={g}")}
<p style="margin:16px 0 0;font-size:13px;color:{_MUTED};">Pro tip: Try mixing subjects.
Monday ko Maths, Wednesday ko English, Friday ko Hindi. Variety keeps kids engaged.</p>
<p style="margin:16px 0 0;">&mdash; Team Skolar</p>
"""
    return subject, _wrap_email("Popular This Week", body)


def _build_email_5(
    parent_name: str,
    child_name: str,
    grade: str,
    worksheets_generated: int,
    subjects_tried: int,
    topics_covered: int,
) -> tuple[str, str]:
    """Day 7 — upgrade nudge."""
    app = _get_app_url()
    p = escape(parent_name or "there")
    c = escape(child_name or "your child")

    if worksheets_generated >= 3:
        habit_block = (
            f"<p style='margin:0 0 16px;'>{c} is building a great practice habit! "
            "But 5 worksheets per month se regular practice mushkil hai. "
            "That's why most serious parents upgrade to Scholar:</p>"
        )
    else:
        habit_block = (
            f"<p style='margin:0 0 16px;'>{c} ke liye practice abhi shuru ho rahi hai. "
            "To get the most out of Skolar, here's what Scholar gives you:</p>"
        )

    subject = f"{p}, you've used {worksheets_generated} of 5 free worksheets"
    body = f"""
<p style="margin:0 0 16px;">Hi {p},</p>
<p style="margin:0 0 16px;">It's been a week since you joined Skolar. Here's your progress:</p>
<ul style="margin:0 0 16px;padding-left:20px;">
  <li>Worksheets generated: {worksheets_generated} / 5 (free tier)</li>
  <li>Subjects tried: {subjects_tried}</li>
  <li>Topics covered: {topics_covered}</li>
</ul>
{habit_block}
<p style="margin:0 0 8px;font-weight:700;">Scholar Plan &mdash; &#8377;199/month</p>
<ul style="margin:0 0 16px;padding-left:20px;">
  <li>Unlimited worksheets (no 5/month cap)</li>
  <li>Photo grading &mdash; click photo, get instant score</li>
  <li>Revision notes + flashcards for every topic</li>
  <li>Full progress tracking with mastery levels</li>
  <li>Up to 5 children on one account</li>
  <li>Ask Skolar &mdash; AI tutor for doubts</li>
</ul>
<p style="margin:0 0 16px;">&#8377;199/month = &#8377;6.6/day. Ek chai se bhi kam.</p>
{_cta_button("Upgrade to Scholar &mdash; &#8377;199/month &rarr;", f"{app}/pricing")}
<p style="margin:16px 0 0;">Or save more with annual: &#8377;1,499/year (&#8377;125/month).
That's &#8377;889 ki savings &mdash; almost 5 months free.</p>
<p style="margin:8px 0 16px;"><a href="{app}/pricing?plan=annual"
  style="color:{_GREEN};font-weight:700;text-decoration:underline;">See annual plan (&#8377;125/month) &rarr;</a></p>
<p style="margin:0 0 16px;">Not ready? No problem. Your 5 free worksheets reset every month.
Keep using Skolar, bilkul free. We're here when you need more.</p>
<p style="margin:0 0 0;">&mdash; Team Skolar</p>
<p style="margin:8px 0 0;font-size:13px;color:{_MUTED};">P.S. Reply to this email with any questions.
Real humans read it. Hum yahan hain aapke liye.</p>
"""
    return subject, _wrap_email("Upgrade to Scholar", body)


# ── Public API ───────────────────────────────────────────────────────────────


async def send_welcome_email_1(
    db,
    user_id: str,
    email: str,
    parent_name: str = "",
    child_name: str = "",
    grade: str = "",
) -> None:
    """Send Email 1 immediately and insert the sequence tracking row."""
    subject, html = _build_email_1(parent_name, child_name, grade)

    try:
        await _send_email(email, subject, html)
        logger.info("[WelcomeEmails] Email 1 sent to %s (user %s)", email, user_id)
    except Exception:
        logger.exception("[WelcomeEmails] Failed to send Email 1 to %s", email)
        raise

    # Insert sequence row — ON CONFLICT DO NOTHING prevents restarts
    db.table("email_sequence").upsert(
        {
            "user_id": user_id,
            "user_email": email,
            "parent_name": parent_name,
            "child_name": child_name,
            "child_grade": grade,
            "last_email_sent": 1,
            "next_send_at": "placeholder",  # will be overwritten by RPC below
        },
        on_conflict="user_id",
        ignore_duplicates=True,
    ).execute()

    # Set next_send_at with server-side now() via raw SQL
    # delay_hours is from our own _DELAYS_HOURS dict (int), not user input
    delay_hours = _DELAYS_HOURS[1]
    query = (  # noqa: S608
        f"UPDATE email_sequence SET next_send_at = now() + interval '{delay_hours} hours', "  # noqa: S608
        "last_email_sent = 1 WHERE user_id = $1 AND last_email_sent <= 1"
    )
    db.rpc("execute_sql", {"query": query, "params": [user_id]}).execute()


async def process_pending_emails(db) -> dict:
    """Process all due emails in the sequence. Returns counts."""
    # Fetch rows due for sending
    result = (
        db.table("email_sequence").select("*").eq("completed", False).lte("next_send_at", "now()").limit(50).execute()
    )

    rows = result.data or []
    processed = len(rows)
    sent = 0
    skipped = 0

    for row in rows:
        user_id = row["user_id"]
        email = row["user_email"]
        parent_name = row.get("parent_name", "")
        child_name = row.get("child_name", "")
        grade = row.get("child_grade", "")
        last_sent = row["last_email_sent"]
        next_email = last_sent + 1

        if next_email > 5:
            # Sequence complete
            _mark_completed(db, user_id)
            skipped += 1
            continue

        # Check subscription tier — skip remaining if paid
        if next_email >= 3:
            tier = _get_user_tier(db, user_id)
            if tier == "paid":
                _mark_completed(db, user_id)
                skipped += 1
                logger.info("[WelcomeEmails] User %s upgraded — marking sequence complete", user_id)
                continue

        # Fetch usage stats for personalised content
        stats = _get_user_stats(db, user_id)

        # Email 2 skip: if user already generated worksheets, advance past it
        if next_email == 2 and stats["worksheets_generated"] > 0:
            logger.info("[WelcomeEmails] Skipping Email 2 for user %s (has worksheets)", user_id)
            _advance_sequence(db, user_id, email_number=2)
            skipped += 1
            continue

        # Build and send
        try:
            subject, html = _build_for_number(
                next_email,
                parent_name,
                child_name,
                grade,
                stats,
            )
            await _send_email(email, subject, html)
            _advance_sequence(db, user_id, email_number=next_email)
            sent += 1
            logger.info("[WelcomeEmails] Email %d sent to %s", next_email, email)
        except Exception:
            logger.exception("[WelcomeEmails] Failed Email %d for user %s", next_email, user_id)
            skipped += 1

    return {"processed": processed, "sent": sent, "skipped": skipped}


# ── Internal helpers ─────────────────────────────────────────────────────────


def _build_for_number(
    n: int,
    parent_name: str,
    child_name: str,
    grade: str,
    stats: dict,
) -> tuple[str, str]:
    """Dispatch to the correct template builder."""
    wg = stats.get("worksheets_generated", 0)
    if n == 2:
        return _build_email_2(parent_name, child_name, grade)
    if n == 3:
        return _build_email_3(parent_name, child_name, grade, wg)
    if n == 4:
        return _build_email_4(parent_name, child_name, grade, wg)
    if n == 5:
        return _build_email_5(
            parent_name,
            child_name,
            grade,
            wg,
            stats.get("subjects_tried", 0),
            stats.get("topics_covered", 0),
        )
    raise ValueError(f"Unknown email number: {n}")


def _get_user_tier(db, user_id: str) -> str:
    """Return 'free' or 'paid'."""
    result = db.table("user_subscriptions").select("tier").eq("user_id", user_id).maybe_single().execute()
    if result.data:
        return result.data.get("tier", "free")
    return "free"


def _get_user_stats(db, user_id: str) -> dict:
    """Fetch worksheet usage stats for personalisation."""
    # Count worksheets
    ws_result = db.table("worksheets").select("subject, topic", count="exact").eq("user_id", user_id).execute()
    worksheets = ws_result.data or []
    worksheets_generated = len(worksheets)
    subjects_tried = len({w.get("subject") for w in worksheets if w.get("subject")})
    topics_covered = len({w.get("topic") for w in worksheets if w.get("topic")})

    return {
        "worksheets_generated": worksheets_generated,
        "subjects_tried": subjects_tried,
        "topics_covered": topics_covered,
    }


def _advance_sequence(db, user_id: str, email_number: int) -> None:
    """Update last_email_sent and set next_send_at, or mark completed."""
    if email_number >= 5:
        _mark_completed(db, user_id)
        return

    delay_hours = _DELAYS_HOURS.get(email_number, 48)
    db.table("email_sequence").update(
        {
            "last_email_sent": email_number,
        }
    ).eq("user_id", user_id).execute()

    # Use RPC for server-side time calculation
    # delay_hours is from our own _DELAYS_HOURS dict (int), not user input
    query = f"UPDATE email_sequence SET next_send_at = now() + interval '{delay_hours} hours' WHERE user_id = $1"  # noqa: S608
    db.rpc("execute_sql", {"query": query, "params": [user_id]}).execute()


def _mark_completed(db, user_id: str) -> None:
    """Mark the sequence as completed."""
    db.table("email_sequence").update(
        {
            "completed": True,
            "next_send_at": None,
        }
    ).eq("user_id", user_id).execute()
