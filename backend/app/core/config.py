from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = "Skolar"
    debug: bool = False

    # Supabase
    supabase_url: str
    supabase_service_key: str

    # OpenAI (kept for fallback)
    openai_api_key: str = ""

    # Gemini
    gemini_api_key: str = ""
    llm_provider: str = "gemini"

    # Resend (email delivery)
    resend_api_key: str = ""
    resend_from_email: str = "onboarding@resend.dev"

    # Monitoring
    sentry_dsn: str = ""  # Empty = disabled
    log_level: str = "INFO"
    log_json: bool = True  # JSON in prod, human-readable in dev

    # Quality scoring
    worksheet_export_min_score: int = 70  # 0-100; PDF export blocked below this

    # CORS — comma-separated allowed origins
    frontend_url: str = "https://ed-tech-drab.vercel.app"
    cors_origins: str = (
        "http://localhost:5173,http://localhost:3000,http://localhost:5174,https://ed-tech-drab.vercel.app"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
