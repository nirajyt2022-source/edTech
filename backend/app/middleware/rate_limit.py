"""
Rate limiting middleware using SlowAPI.

Limits are per-user (via Supabase JWT) or per-IP for unauthenticated requests.
Gracefully degrades to a no-op limiter if slowapi is not installed (e.g. in tests).
"""

import logging

from fastapi import Request, Response
from starlette.responses import JSONResponse

logger = logging.getLogger("skolar.rate_limit")

try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    _SLOWAPI_AVAILABLE = True
except ImportError:
    _SLOWAPI_AVAILABLE = False
    RateLimitExceeded = None  # type: ignore[assignment,misc]


def _get_user_or_ip(request: Request) -> str:
    """Extract user ID from auth header, fall back to IP address."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 20:
        import hashlib

        token_hash = hashlib.sha256(auth.encode()).hexdigest()[:12]
        return f"user:{token_hash}"
    if _SLOWAPI_AVAILABLE:
        return f"ip:{get_remote_address(request)}"
    return "ip:unknown"


if _SLOWAPI_AVAILABLE:
    limiter = Limiter(key_func=_get_user_or_ip)
else:

    class _NoOpLimiter:
        """Dummy limiter that does nothing when slowapi is missing."""

        def limit(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def shared_limit(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    limiter = _NoOpLimiter()  # type: ignore[assignment]
    logger.warning("slowapi not installed — rate limiting disabled")


def rate_limit_exceeded_handler(request: Request, exc) -> Response:
    """Custom handler for rate limit errors."""
    logger.warning(
        "Rate limit exceeded",
        extra={"key": _get_user_or_ip(request), "path": request.url.path},
    )
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please slow down.",
            "retry_after": str(getattr(exc, "detail", "")),
        },
    )
