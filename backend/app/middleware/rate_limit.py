"""
Rate limiting middleware using SlowAPI.

Limits are per-user (via Supabase JWT) or per-IP for unauthenticated requests.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
from starlette.responses import JSONResponse
import logging

logger = logging.getLogger("skolar.rate_limit")


def _get_user_or_ip(request: Request) -> str:
    """Extract user ID from auth header, fall back to IP address."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 20:
        # Use a hash of the token as the key (don't log the actual token)
        import hashlib
        token_hash = hashlib.md5(auth.encode()).hexdigest()[:12]
        return f"user:{token_hash}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_get_user_or_ip)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Custom handler for rate limit errors."""
    logger.warning(
        "Rate limit exceeded",
        extra={"key": _get_user_or_ip(request), "path": request.url.path},
    )
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please slow down.",
            "retry_after": str(exc.detail),
        },
    )
