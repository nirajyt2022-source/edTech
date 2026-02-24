"""
Request ID middleware — assigns a unique ID to every request for tracing.
"""
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or use provided request ID
        request_id = request.headers.get("x-request-id", str(uuid.uuid4())[:8])

        # Bind to structlog context (available in all log calls during this request)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        # Add user info if authenticated
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            import hashlib
            user_hash = hashlib.md5(auth.encode()).hexdigest()[:8]
            structlog.contextvars.bind_contextvars(user=user_hash)

        response = await call_next(request)

        # Add request ID to response headers (for client-side debugging)
        response.headers["x-request-id"] = request_id

        return response
