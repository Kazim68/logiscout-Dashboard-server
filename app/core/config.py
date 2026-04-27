"""
Application Configuration Module
Loads environment variables and provides configuration settings.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional, List


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Uses pydantic-settings for validation and type coercion.
    """
    
    # Application Settings
    APP_NAME: str = "LogiScout API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # MongoDB Configuration
    MONGO_URI: str
    DATABASE_NAME: str
    
    # JWT Configuration
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Google OAuth Configuration
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    
    # GitHub OAuth Configuration
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    GITHUB_REDIRECT_URI: str
    
    # CORS Configuration
    FRONTEND_URL: str = "http://localhost:4001"
    FRONTEND_URLS: str = "http://localhost:4001,http://127.0.0.1:4001"

    # Ingestion Server
    INGESTION_SERVER_BASE_URL: str = "http://localhost:8001"
    
    # SMTP / Email Configuration (optional — OTP is logged to console if not set)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    
    # OTP Configuration
    OTP_LENGTH: int = 6
    OTP_EXPIRE_MINUTES: int = 10
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached settings instance.
    Uses lru_cache to avoid reading .env file on every request.
    """
    return Settings()


# Export settings instance for convenience
settings = get_settings()


def get_allowed_origins() -> List[str]:
    """Return normalized frontend origins for CORS middleware."""
    origins = [origin.strip() for origin in settings.FRONTEND_URLS.split(",") if origin.strip()]
    if settings.FRONTEND_URL and settings.FRONTEND_URL not in origins:
        origins.append(settings.FRONTEND_URL)
    return origins
