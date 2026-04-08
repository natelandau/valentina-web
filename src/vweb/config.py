"""Application configuration via pydantic-settings."""

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from vweb.constants import LogLevel


def _default_workers() -> int:
    """Compute default gunicorn workers: (2 x CPU cores) + 1."""
    return (os.cpu_count() or 1) * 2 + 1


class RedisSettings(BaseModel):
    """Redis connection settings shared by Flask-Caching and Flask-Session."""

    url: str = "redis://127.0.0.1:6379/0"
    default_timeout: int = 300
    key_prefix: str = "vweb:"


class OAuthProviderSettings(BaseModel):
    """OAuth provider credentials."""

    client_id: str = ""
    client_secret: str = ""


class OAuthSettings(BaseModel):
    """OAuth configuration for all supported providers."""

    discord: OAuthProviderSettings = Field(default_factory=OAuthProviderSettings)
    github: OAuthProviderSettings = Field(default_factory=OAuthProviderSettings)
    google: OAuthProviderSettings = Field(default_factory=OAuthProviderSettings)


class APISettings(BaseModel):
    """API settings."""

    base_url: str
    api_key: str
    default_company_id: str
    server_admin_user_id: str
    timeout: float = Field(default=10.0)
    max_retries: int = Field(default=5)
    retry_delay: float = Field(default=1.0)
    auto_retry_rate_limit: bool = Field(default=True)
    auto_idempotency_keys: bool = Field(default=True)
    enable_logs: bool = Field(default=False)


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env.secret",
        env_file_encoding="utf-8",
        env_prefix="VWEB_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    app_name: str = "Valentina Web"
    debug_toolbar: bool = False
    env: Literal["development", "production"] = "production"
    secret_key: str = "change-me-in-production"  # noqa: S105
    host: str = "127.0.0.1"
    port: int = 8089

    access_log: str = "-"
    workers: int = Field(default_factory=_default_workers)

    redis: RedisSettings = Field(default_factory=RedisSettings)

    log_file_path: Path | None = None
    log_level: LogLevel = LogLevel.INFO

    oauth: OAuthSettings = Field(default_factory=OAuthSettings)

    api: APISettings

    @model_validator(mode="after")
    def _validate_production_requires_redis(self) -> "Settings":
        if self.env == "production" and not self.redis.url:
            msg = "redis.url is required when env is production"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_production_secret_key(self) -> "Settings":
        if self.env == "production" and self.secret_key == "change-me-in-production":  # noqa: S105
            msg = "secret_key must not be the default value in production"
            raise ValueError(msg)
        return self


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the application settings singleton, creating it on first access.

    Returns:
        The application settings instance.
    """
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()  # ty:ignore[missing-argument]
    return _settings
