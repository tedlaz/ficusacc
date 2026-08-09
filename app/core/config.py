"""Application configuration using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "HomeAccounting"
    DEBUG: bool = False
    # Database
    DATABASE_URL: str = "sqlite:///./accounting.db"
    BACKUP_DIR: str = "./backups"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    SESSION_COOKIE_SECURE: bool = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
