from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # AI providers (Gemini for text + live voice; OpenRouter/Groq for text)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_model_fallback: str = "gemini-1.5-flash"
    gemini_live_model: str = "gemini-3.8-live"
    gemini_live_voice: str = "Charon"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    jarvis_ai_provider: str = "auto"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    environment: str = Field(default="development", pattern="^(development|staging|production)$")

    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"

    # Security
    jarvis_api_token: str = ""
    secret_key: str = ""
    token_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 30  # 30 days

    # Database
    jarvis_db_path: str = "data/jarvis.sqlite3"

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_default: str = "100/minute"

    # Features
    enable_server_history: bool = False
    enable_memory_suggestions: bool = False
    enable_tools: bool = True

    # Research
    research_cache_ttl: int = 300  # 5 minutes
    research_timeout: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator('jarvis_api_token')
    @classmethod
    def validate_token(cls, v):
        if v and len(v) < 32 and not v.startswith("replace_"):
            raise ValueError("jarvis_api_token must be at least 32 characters")
        return v

    @field_validator('secret_key')
    @classmethod
    def validate_secret(cls, v):
        if v and len(v) < 32 and not v.startswith("replace_"):
            raise ValueError("secret_key must be at least 32 characters")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
