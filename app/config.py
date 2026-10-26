from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    groq_api_key: str = ""
    jarvis_ai_provider: str = "auto"
    openrouter_model: str = "openai/gpt-4o-mini"
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_model: str = "gemini-2.5-flash"
    gemini_live_model: str = "gemini-3.8-live"
    gemini_live_voice: str = "Aoede"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    jarvis_api_token: str = ""
    jarvis_db_path: str = "data/jarvis.sqlite3"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
