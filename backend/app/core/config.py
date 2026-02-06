from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_name: str = "PracticeCraft AI"
    debug: bool = False

    # Supabase
    supabase_url: str
    supabase_service_key: str

    # OpenAI
    openai_api_key: str

    # CORS
    frontend_url: str = "http://localhost:5173"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
