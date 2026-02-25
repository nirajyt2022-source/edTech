"""
Security event logging.

Structured log entries for auth failures, rate-limit hits, injection attempts,
and subscription bypasses. Enables future alerting / SIEM integration.
"""

import logging

logger = logging.getLogger("skolar.security")


def log_security_event(
    event_type: str,
    *,
    user_id: str | None = None,
    detail: str = "",
) -> None:
    """Emit a structured security log entry."""
    logger.warning(
        "security_event type=%s user=%s detail=%s",
        event_type,
        user_id or "anonymous",
        detail[:200],
    )
