from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import health, worksheets, syllabus, children, subscription
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


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
    }
