import json as _json
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging_config import setup_logging
from app.middleware.rate_limit import RateLimitExceeded, limiter, rate_limit_exceeded_handler

# Initialize structured logging first
setup_logging()

settings = get_settings()
_lifespan_logger = structlog.get_logger("skolar.lifespan")

# Initialize Sentry (only if DSN is configured)
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment="production" if not settings.debug else "development",
    )

# Lazy router imports (after logging is set up)
from app.api import (  # noqa: E402
    analytics,
    ask_skolar,
    cbse_syllabus,
    children,
    classes,
    curriculum,
    dashboard,
    engagement,
    feedback,
    flashcards,
    grading,
    health,
    insights,
    learning_graph,
    reports,
    revision,
    saved_worksheets,
    share,
    subscription,
    syllabus,
    textbook,
    topic_preferences,
    users,
)
from app.api.worksheets_v2 import router as worksheets_v2_router  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: warm singletons so config errors surface at boot, not first request."""
    import time as _time

    _lifespan_logger.info("startup_begin", version="0.1.0")

    from app.core.deps import get_supabase_client
    from app.services.ai_client import get_ai_client

    get_supabase_client()
    _lifespan_logger.info("supabase_client_ready")

    get_ai_client()
    _lifespan_logger.info("ai_client_ready")

    _lifespan_logger.info("startup_complete")
    yield

    # ── Graceful shutdown ─────────────────────────────────────
    _t0 = _time.monotonic()
    _lifespan_logger.info("shutdown_begin")

    # 1. Clear Gemini context cache
    try:
        from app.services.ai_client import _cached_contents

        n_cached = len(_cached_contents)
        _cached_contents.clear()
        _lifespan_logger.info("gemini_cache_cleared", entries=n_cached)
    except Exception as e:
        _lifespan_logger.warning("gemini_cache_clear_failed", error=str(e))

    # 2. Log AI client stats summary (with full LLMOps metrics)
    try:
        from app.services.ai_client import get_llm_metrics

        metrics = get_llm_metrics()
        _lifespan_logger.info(
            "ai_client_stats",
            total_calls=metrics["total_calls"],
            total_errors=metrics["total_errors"],
            error_rate=metrics["error_rate"],
            avg_latency_ms=metrics["avg_latency_ms"],
            total_input_tokens=metrics["total_input_tokens"],
            total_output_tokens=metrics["total_output_tokens"],
            estimated_cost_usd=metrics["estimated_cost_usd"],
            cache_hit_rate=metrics["cache_hit_rate"],
        )
    except Exception as e:
        _lifespan_logger.warning("ai_stats_log_failed", error=str(e))

    # 3. Flush Sentry events
    try:
        sentry_sdk.flush(timeout=5)
        _lifespan_logger.info("sentry_flushed")
    except Exception as e:
        _lifespan_logger.warning("sentry_flush_failed", error=str(e))

    _elapsed_ms = int((_time.monotonic() - _t0) * 1000)
    _lifespan_logger.info("shutdown_complete", elapsed_ms=_elapsed_ms)


class UnicodeJSONResponse(JSONResponse):
    """JSONResponse that serialises with ensure_ascii=False so Devanagari
    (and all other non-ASCII Unicode) is sent as real UTF-8 characters
    rather than \\uXXXX escape sequences."""

    def render(self, content: object) -> bytes:
        return _json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")


app = FastAPI(
    title=settings.app_name,
    description="AI-powered worksheet generation platform for educators",
    version="0.1.0",
    default_response_class=UnicodeJSONResponse,
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
if RateLimitExceeded is not None:
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Request tracing + access logging middleware (outermost first)
from app.middleware.access_log import AccessLogMiddleware  # noqa: E402
from app.middleware.request_id import RequestIDMiddleware  # noqa: E402
from app.middleware.security_headers import SecurityHeadersMiddleware  # noqa: E402

# Configure CORS — always include frontend_url
# IMPORTANT: CORSMiddleware must be added LAST so it executes FIRST
# (Starlette processes middleware in reverse order of addition)
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
if settings.frontend_url and settings.frontend_url not in cors_origins:
    cors_origins.append(settings.frontend_url)

# Add BaseHTTPMiddleware classes first (they run AFTER CORS)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# CORS last = runs first — handles OPTIONS preflight before other middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# Include routers
app.include_router(health.router)
app.include_router(syllabus.router)
app.include_router(children.router)
app.include_router(subscription.router)
app.include_router(cbse_syllabus.router)
app.include_router(topic_preferences.router)
app.include_router(engagement.router)
app.include_router(users.router)
app.include_router(classes.router)
app.include_router(curriculum.router)
app.include_router(analytics.router)
app.include_router(dashboard.router)
app.include_router(saved_worksheets.router)
app.include_router(share.router)
app.include_router(learning_graph.router)
app.include_router(reports.router)
app.include_router(worksheets_v2_router)
app.include_router(grading.router)
app.include_router(revision.router)
app.include_router(flashcards.router)
app.include_router(textbook.router)
app.include_router(ask_skolar.router)
app.include_router(insights.router)
app.include_router(feedback.router)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
    }
