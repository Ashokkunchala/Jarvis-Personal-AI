from functools import lru_cache
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # API Keys
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_model_fallback: str = "gemini-1.5-flash"
    
    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    
    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
    
    # Security
    jarvis_api_token: str = ""
    secret_key: str = Field(default="", min_length=32)
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
    def allowed_origins(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
    
    @field_validator('jarvis_api_token')
    @classmethod
    def validate_token(cls, v):
        if v and len(v) < 32 and not v.startswith("replace_"):
            raise ValueError("jarvis_api_token must be at least 32 characters")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
