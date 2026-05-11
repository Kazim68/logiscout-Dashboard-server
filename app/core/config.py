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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    CHAT_ENCRYPTION_KEY: str = ""
    
    # Google OAuth Configuration
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    
    # GitHub OAuth Configuration
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    GITHUB_REDIRECT_URI: str
    
    # CORS Configuration
    # FRONTEND_URL: primary frontend origin (used for OAuth redirects + CORS).
    # EXTRA_ALLOWED_ORIGINS: optional comma-separated list of additional origins
    # (e.g. local dev, custom domain). Whitespace and trailing slashes are stripped.
    FRONTEND_URL: str = "https://logiscout.vercel.app"
    EXTRA_ALLOWED_ORIGINS: str = ""

    # Ingestion Server
    INGESTION_SERVER_BASE_URL: str
    RAG_SERVER_BASE_URL: str
    
    # SMTP / Email Configuration (optional — OTP is logged to console if not set)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    
    # OTP Configuration
    OTP_LENGTH: int = 6
    OTP_EXPIRE_MINUTES: int = 10

    # Password Reset Configuration
    RESET_CODE_EXPIRE_MINUTES: int = 15
    
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


def _normalize_origin(origin: str) -> str:
    """Strip whitespace and any trailing slash — CORS does exact origin matching."""
    return origin.strip().rstrip("/")


def get_allowed_origins() -> List[str]:
    """Return normalized frontend origins for CORS middleware.

    Sources, in order:
    1. FRONTEND_URL (primary)
    2. EXTRA_ALLOWED_ORIGINS (comma-separated)
    3. Hardcoded production fallback so a misconfigured env var can't lock
       the deployed frontend out of its own backend.
    4. Localhost dev origins when DEBUG is on.
    """
    origins: List[str] = []

    if settings.FRONTEND_URL:
        origins.append(_normalize_origin(settings.FRONTEND_URL))

    if settings.EXTRA_ALLOWED_ORIGINS:
        origins.extend(
            _normalize_origin(o)
            for o in settings.EXTRA_ALLOWED_ORIGINS.split(",")
            if o.strip()
        )

    # Always allow the production frontend, even if FRONTEND_URL was set
    # to something else (e.g. a preview deployment).
    origins.append("https://logiscout-frontend.vercel.app")

    if settings.DEBUG:
        origins.extend([
            "http://localhost:3000",
            "http://localhost:4001",
            "http://127.0.0.1:3000",
        ])

    # De-duplicate while preserving order.
    seen = set()
    result: List[str] = []
    for o in origins:
        if o and o not in seen:
            seen.add(o)
            result.append(o)
    return result


def get_allowed_origin_regex() -> str:
    """Match Vercel preview deployments (per-PR URLs) for the frontend project."""
    return r"^https://logiscout-frontend(-[a-z0-9-]+)?\.vercel\.app$"
