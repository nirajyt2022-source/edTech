from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import health, worksheets, syllabus, children, subscription, cbse_syllabus, topic_preferences, engagement, users, classes, curriculum, analytics, dashboard
from app.api.worksheets_v1 import router as worksheets_v1_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="AI-powered worksheet generation platform for educators",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",  # Vite dev server
        "http://localhost:5174",  # Vite dev server (alternate port)
        "https://ed-tech-drab.vercel.app",  # Production frontend
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(worksheets.router)
app.include_router(syllabus.router)
app.include_router(children.router)
app.include_router(subscription.router)
app.include_router(cbse_syllabus.router)
app.include_router(topic_preferences.router)
app.include_router(engagement.router)
app.include_router(users.router)
app.include_router(classes.router)
app.include_router(curriculum.router)
app.include_router(worksheets_v1_router)
app.include_router(analytics.router)
app.include_router(dashboard.router)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
    }
