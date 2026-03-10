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
    INTEGRATION_WEBHOOK_SECRET: str = ""  # shared HMAC secret for Zoho/QB webhooks
    ZOHO_WEBHOOK_SECRET: str = ""  # static token for Zoho (falls back to INTEGRATION_WEBHOOK_SECRET)
    INTEGRATION_ALLOWED_SOURCES: str = "zoho,qb"  # comma-separated
    INTEGRATION_HMAC_SKEW_SECONDS: int = 300  # replay protection window
    FEATURE_SAMANTHA: str = "false"  # "true" to show AI/Samantha nav item
    TRUE911_BOOTSTRAP_ADMIN_PASSWORD: str = ""  # required for prod bootstrap
    TRUE911_BOOTSTRAP_SUPERADMIN_EMAIL: str = "smanley@manleysolutions.com"
    ALLOW_PUBLIC_REGISTRATION: bool = False  # env flag, default off
    SEED_DEMO: str = "false"  # explicit "true" to seed demo data

    # ── Verizon ThingSpace ─────────────────────────────────────────────
    VERIZON_THINGSPACE_AUTH_MODE: str = ""  # oauth_client_credentials | api_key_secret_token | legacy_short_key_secret | username_password_session
    VERIZON_THINGSPACE_BASE_URL: str = "https://thingspace.verizon.com/api"
    VERIZON_THINGSPACE_OAUTH_TOKEN_PATH: str = "/ts/v1/oauth2/token"  # path appended to base_url
    VERIZON_THINGSPACE_ACCOUNT_NAME: str = ""
    # oauth_client_credentials
    VERIZON_THINGSPACE_CLIENT_ID: str = ""
    VERIZON_THINGSPACE_CLIENT_SECRET: str = ""
    # api_key_secret_token
    VERIZON_THINGSPACE_API_KEY: str = ""
    VERIZON_THINGSPACE_API_SECRET: str = ""
    VERIZON_THINGSPACE_API_TOKEN: str = ""
    VERIZON_THINGSPACE_APP_TOKEN_HEADER: str = "VZ-M2M-Token"  # or "App-Token"
    # M2M endpoint auth strategy (controls how headers are sent on protected requests)
    # oauth_plus_vz_m2m (default) | oauth_plus_app_token | oauth_plus_both | bearer_only | session_token_legacy
    VERIZON_THINGSPACE_M2M_AUTH_MODE: str = ""
    # Override account ID for M2M endpoints (falls back to ACCOUNT_NAME)
    # ThingSpace Key Management keyset IDs are NOT the same as M2M account names.
    # M2M account names are typically "NNNNNNNNNN-NNNNN" format.
    VERIZON_THINGSPACE_M2M_ACCOUNT_ID: str = ""
    # legacy_short_key_secret
    VERIZON_THINGSPACE_SHORT_KEY: str = ""
    VERIZON_THINGSPACE_SHORT_SECRET: str = ""
    # username_password_session
    VERIZON_THINGSPACE_USERNAME: str = ""
    VERIZON_THINGSPACE_PASSWORD: str = ""

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
