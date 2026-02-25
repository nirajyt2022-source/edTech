"""
Access logging middleware — logs every request with timing.
"""

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("skolar.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()

        try:
            response = await call_next(request)
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            # Log all non-health requests
            if request.url.path not in ("/health", "/health/deep"):
                logger.info(
                    "request",
                    status=response.status_code,
                    latency_ms=elapsed_ms,
                )

            return response

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.error(
                "request_error",
                status=500,
                latency_ms=elapsed_ms,
                error=str(exc),
            )
            raise
