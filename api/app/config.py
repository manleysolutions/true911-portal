from __future__ import annotations

import json
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://true911:true911@localhost:5432/true911"
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    CORS_ORIGINS: list[str] = ["*"]
    APP_MODE: str = "production"  # "demo" | "production" — default is production-safe

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
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def cors_is_wildcard(self) -> bool:
        """True when origins list is effectively a wildcard."""
        return self.CORS_ORIGINS == ["*"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v):
        """Accept a JSON array, comma-separated string, or bare '*' from env.

        Examples that all work:
            *
            https://example.com
            https://a.com,https://b.com
            ["https://a.com","https://b.com"]
        Trailing slashes are stripped to avoid origin-mismatch bugs.
        """
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [s.strip().rstrip("/") for s in parsed if s.strip()]
                except json.JSONDecodeError:
                    pass
            return [s.strip().rstrip("/") for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return [s.strip().rstrip("/") if isinstance(s, str) else s for s in v]
        return v


settings = Settings()
