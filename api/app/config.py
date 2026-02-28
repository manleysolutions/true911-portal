from __future__ import annotations

import json
from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://true911:true911@localhost:5432/true911"
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    CORS_ORIGINS: str = "*"  # str — parsed into a list by cors_origin_list
    APP_MODE: str = "production"  # "demo" | "production" — default is production-safe
    REDIS_URL: str = ""  # redis://localhost:6379/0 — set in Render env
    FEATURE_SAMANTHA: str = "false"  # "true" to show AI/Samantha nav item

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        """Return an asyncpg-compatible connection string.

        Render provides DATABASE_URL with the ``postgres://`` or
        ``postgresql://`` scheme.  SQLAlchemy's async driver needs
        ``postgresql+asyncpg://``, so we normalise here.
        """
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @cached_property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS_ORIGINS string into a list.

        Accepts any of these formats from the env var:
            *
            https://example.com
            https://a.com,https://b.com
            ["https://a.com","https://b.com"]
        Trailing slashes are stripped to avoid origin-mismatch bugs.
        """
        raw = self.CORS_ORIGINS.strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [s.strip().rstrip("/") for s in parsed if s.strip()]
            except json.JSONDecodeError:
                pass
        return [s.strip().rstrip("/") for s in raw.split(",") if s.strip()]

    @property
    def cors_is_wildcard(self) -> bool:
        """True when origins list is effectively a wildcard."""
        return self.cors_origin_list == ["*"]


settings = Settings()
