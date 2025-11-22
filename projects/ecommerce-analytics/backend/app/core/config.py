"""
Configuration settings for E-commerce Analytics Platform

Uses Pydantic Settings for environment variable validation.
"""

from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings can be overridden via .env file or environment variables.
    """

    # App Info
    APP_NAME: str = "E-commerce Analytics Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENV: str = "development"  # development, staging, production

    # API Settings
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "CHANGE-THIS-IN-PRODUCTION-USE-STRONG-SECRET"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",  # React dev server
        "http://localhost:8000",  # FastAPI
        "https://yourdomain.com"   # Production frontend
    ]

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ecommerce_analytics"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 300  # 5 minutes

    # Celery (Background Tasks)
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Amazon SP-API
    AMAZON_CLIENT_ID: Optional[str] = None
    AMAZON_CLIENT_SECRET: Optional[str] = None
    AMAZON_REFRESH_TOKEN: Optional[str] = None
    AMAZON_AWS_ACCESS_KEY: Optional[str] = None
    AMAZON_AWS_SECRET_KEY: Optional[str] = None
    AMAZON_ROLE_ARN: Optional[str] = None
    AMAZON_MARKETPLACE_ID: str = "ATVPDKIKX0DER"  # US marketplace

    # Shopify API
    SHOPIFY_SHOP_NAME: Optional[str] = None
    SHOPIFY_ACCESS_TOKEN: Optional[str] = None
    SHOPIFY_API_VERSION: str = "2024-01"

    # Walmart Marketplace API
    WALMART_CLIENT_ID: Optional[str] = None
    WALMART_CLIENT_SECRET: Optional[str] = None

    # Email (SendGrid)
    SENDGRID_API_KEY: Optional[str] = None
    FROM_EMAIL: str = "alerts@yourdomain.com"
    ALERT_EMAIL_RECIPIENTS: List[str] = []

    # Slack Notifications
    SLACK_WEBHOOK_URL: Optional[str] = None

    # Monitoring
    SENTRY_DSN: Optional[str] = None
    LOG_LEVEL: str = "INFO"

    # ML Models
    MODEL_PATH: str = "./models"
    ENABLE_FORECASTING: bool = True
    FORECAST_HORIZON_DAYS: int = 30

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()


# Global settings instance
settings = get_settings()
