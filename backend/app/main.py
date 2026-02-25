import json as _json

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging_config import setup_logging
from app.middleware.rate_limit import RateLimitExceeded, limiter, rate_limit_exceeded_handler

# Initialize structured logging first
setup_logging()

settings = get_settings()

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
    flashcards,
    grading,
    health,
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


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
    }
