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
    FEATURE_LINE_INTELLIGENCE: str = "false"  # "true" to enable Line Intelligence Engine endpoints
    TRUE911_BOOTSTRAP_ADMIN_PASSWORD: str = ""  # required for prod bootstrap
    TRUE911_BOOTSTRAP_SUPERADMIN_EMAIL: str = "smanley@manleysolutions.com"
    ALLOW_PUBLIC_REGISTRATION: bool = False  # env flag, default off
    SEED_DEMO: str = "false"  # explicit "true" to seed demo data

    # Comma-separated list of tenant_ids that count as the "internal"
    # / platform context.  The Registration review queue, conversion
    # workflow, and any other operator-only surface are gated by this
    # — a user is considered to be in an internal context only if
    # their REAL tenant_id (i.e. ignoring any active impersonation)
    # is in this set, or they are a real SuperAdmin not currently
    # impersonating.  Customer-tenant Admin/DataEntry users do NOT
    # gain access by virtue of their role alone.
    INTERNAL_TENANT_IDS: str = "default"

    # ── AI Support Assistant ─────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""  # empty = rule-based fallback (no LLM calls)

    # ── LLLM (Phase 1: read-only AI Health Summary) ───────────────
    # Master switch.  When "false" (default) every /api/llm route
    # returns 404, the UI surface is hidden, and no provider call is
    # ever made — the platform behaves exactly as it did before Phase 1.
    FEATURE_LLLM: str = "false"
    # Provider implementation to use.  "" (default) and "anthropic"
    # both resolve to AnthropicProvider; future values will map to
    # ollama, llamacpp, vllm, azure_openai_gov, bedrock_govcloud, etc.
    LLLM_PROVIDER: str = ""
    # Hard external-egress switch.  Even when FEATURE_LLLM is on, this
    # must additionally be "true" for the orchestrator to call any
    # network provider.  Off → deterministic-fallback only.
    LLLM_ALLOW_EXTERNAL: str = "false"
    # Daily token budget per effective tenant.  0 = unlimited (NOT
    # recommended in prod).  Default 100,000 is conservative for Phase 1;
    # raise after a week of telemetry review.
    LLLM_DAILY_TOKEN_CAP_PER_TENANT: int = 100000
    # Hard per-call timeout for the provider.  Audit requires 3–5 s.
    LLLM_PROVIDER_TIMEOUT_SECONDS: float = 5.0
    # Cache TTL for summary results, keyed on (tenant, scope, fingerprint).
    LLLM_CACHE_TTL_SECONDS: int = 300
    # Default model identifier when the provider supports a choice.
    LLLM_DEFAULT_MODEL: str = "claude-sonnet-4-20250514"

    # ── T-Mobile Callback Ingest (MVP — AI Health Summary only) ──
    # When "false" (default) the T-Mobile PIT callback endpoints in
    # api/app/routers/tmobile_callback.py keep their current
    # logging-only behavior (200 ack, no DB write).  When "true" they
    # additionally archive the raw payload to IntegrationPayload and
    # enqueue a webhook.tmobile job that promotes the payload to
    # Device.last_network_event (the same field Verizon writes),
    # which the Health Normalizer reads as last_carrier_event_at.
    #
    # No other surface (Command Center, Map, Sites, Devices,
    # attention engine, customer portal) reads this flag.  No
    # outbound TAAP call.  No signature verification yet — see
    # docs/TMOBILE_CALLBACK_INGEST_MVP.md "Known gaps".
    FEATURE_TMOBILE_CALLBACK_INGEST: str = "false"
    # Reject promotion (but still archive) if the payload's event
    # timestamp is older than this many seconds.  Defends against
    # replayed callbacks marking long-offline devices as fresh.
    TMOBILE_CALLBACK_MAX_AGE_SECONDS: int = 600

    # ── T-Mobile Callback IP Audit (passive, log-only) ────────────
    # Defense-in-depth for the T-Mobile PIT callback URLs.  When
    # "true", a middleware checks the Cloudflare-provided
    # CF-Connecting-IP header on requests to /tmobile/wholesale/callback/*
    # and emits a single warning log line if the source IP is outside
    # TMOBILE_CALLBACK_SOURCE_IPS.  Never alters the response code
    # (HTTP 200 contract is preserved) — this catches Cloudflare WAF
    # misconfiguration and direct *.onrender.com origin probes that
    # bypass the Cloudflare edge rule.  Silent when CF-Connecting-IP
    # is missing (local dev / direct origin hit with no spoof) and
    # silent when the IP is in the allowlist.  Enforcement lives at
    # Cloudflare; this is observability only.  See
    # docs/TMOBILE_CALLBACK_IP_AUDIT.md (or the rollout doc) for the
    # Cloudflare rule that performs the actual blocking.
    FEATURE_TMOBILE_CALLBACK_IP_AUDIT: str = "false"
    # Comma-separated list of allowed source IPs / ranges / CIDRs for
    # T-Mobile PIT callbacks.  Each entry may be:
    #   * single IPv4:  206.29.176.74
    #   * range:        206.29.176.74-206.29.176.79
    #   * CIDR:         206.29.176.64/27
    # Defaults to the two T-Mobile-confirmed PIT source ranges.
    # Operator override (e.g. to add a test laptop IP during a PIT
    # synthetic) is done via Render env var, not a code change.
    TMOBILE_CALLBACK_SOURCE_IPS: str = (
        "206.29.176.74-206.29.176.79,208.54.104.32-208.54.104.37"
    )

    # ── Health Normalization Layer (MVP — AI Health Summary only) ──
    # When "false" (default) the AI Health Summary uses its existing
    # heartbeat-only derivation in app/services/llm/context.py.  When
    # "true" the orchestrator routes through app/services/health/ —
    # a single canonical state per device fusing heartbeat, carrier
    # telemetry, Telnyx CDR liveness, and VOLA sync timestamps.
    #
    # No other surface (Command Center, Map, Sites, Devices, Attention
    # engine) reads this flag.  Phase N1+ migrations are tracked in
    # docs/HEALTH_NORMALIZER_MVP.md "Rollout plan".
    FEATURE_HEALTH_NORMALIZER: str = "false"

    # ── Hardware-agnostic Device Health layer ──────────────────────
    # When "true", exposes the read-only device-health APIs under
    # /api/device-health (global, property, service-unit, adapter status)
    # and lets the generic sync command persist vendor-enriched status.
    # When "false" (default) the routes return 404 and nothing changes.
    # Vendor logic lives only in app/services/device_health/adapters/* —
    # the core is hardware-agnostic.  Belle Terre / Integrity is the first
    # pilot dataset, not special-cased in code.
    FEATURE_DEVICE_HEALTH: str = "false"

    # ── Zoho Desk (support ticket escalation) ─────────────────────
    ZOHO_DESK_DOMAIN: str = ""  # e.g. https://desk.zoho.com — empty = stub mode
    ZOHO_DESK_ORG_ID: str = ""
    ZOHO_DESK_DEPARTMENT_ID: str = ""
    ZOHO_DESK_CLIENT_ID: str = ""
    ZOHO_DESK_CLIENT_SECRET: str = ""
    ZOHO_DESK_REFRESH_TOKEN: str = ""
    ZOHO_DESK_ACCOUNTS_DOMAIN: str = "https://accounts.zoho.com"

    # ── SMTP Email (password resets, invites) ──────────────────────
    SMTP_HOST: str = ""  # empty = log-only (safe for dev). e.g. smtp.sendgrid.net
    SMTP_PORT: int = 587
    SMTP_USER: str = ""  # e.g. "apikey" for SendGrid
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@true911.com"
    SMTP_FROM_NAME: str = "True911+"
    PUBLIC_URL: str = "https://www.true911.com"  # base URL for email links

    # ── VOLA / FlyingVoice TR-069 ───────────────────────────────────────
    VOLA_BASE_URL: str = "https://cloudapi.volanetworks.net"
    VOLA_EMAIL: str = ""
    VOLA_PASSWORD: str = ""
    VOLA_ORG_ID: str = ""  # optional org to auto-switch
    VOLA_ALLOWED_PARAM_PREFIXES: str = ""  # comma-separated read prefixes
    VOLA_ALLOWED_SET_PREFIXES: str = ""    # comma-separated write prefixes
    VOLA_BLOCKED_SET_PREFIXES: str = ""    # comma-separated blocked write prefixes
    VOLA_DENYLIST_EXACT: str = ""          # comma-separated exact denied nodes
    VOLA_DEBUG_FETCH: str = "false"       # "true" to log raw VOLA API responses

    # ── Zoho CRM ───────────────────────────────────────────────────────
    ZOHO_CRM_CLIENT_ID: str = ""
    ZOHO_CRM_CLIENT_SECRET: str = ""
    ZOHO_CRM_REFRESH_TOKEN: str = ""
    ZOHO_CRM_API_DOMAIN: str = "https://www.zohoapis.com"
    ZOHO_CRM_ACCOUNTS_DOMAIN: str = "https://accounts.zoho.com"
    ZOHO_CRM_ORG_ID: str = ""  # optional — for multi-org Zoho setups
    ZOHO_CRM_DEFAULT_TENANT: str = "default"  # tenant_id for accounts without explicit mapping

    # ── T-Mobile Wholesale (TAAP / PoP) ────────────────────────────────
    TMOBILE_ENV: str = "pit"  # pit | prod
    TMOBILE_BASE_URL: str = ""  # https://pit-apis.t-mobile.com or https://apis.t-mobile.com
    TMOBILE_TOKEN_URL: str = ""  # https://pit-oauth.t-mobile.com/oauth2/v2/tokens or prod equiv
    TMOBILE_CONSUMER_KEY: str = ""
    TMOBILE_CONSUMER_SECRET: str = ""
    TMOBILE_PARTNER_ID: str = ""  # T-Mobile-assigned partner ID
    TMOBILE_SENDER_ID: str = ""   # T-Mobile-assigned sender ID
    TMOBILE_ACCOUNT_ID: str = ""  # wholesale account ID
    TMOBILE_PRIVATE_KEY_PATH: str = ""  # path to RSA private key PEM file
    TMOBILE_PRIVATE_KEY_PEM: str = ""   # alternative: PEM content directly (for Render/Docker)

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
    # oauth_plus_session_token (default) — Bearer + session GUID from /session/login
    # oauth_plus_vz_m2m | oauth_plus_app_token | oauth_plus_both | bearer_only
    VERIZON_THINGSPACE_M2M_AUTH_MODE: str = ""
    # Override account ID for M2M endpoints (falls back to ACCOUNT_NAME)
    # ThingSpace Key Management keyset IDs are NOT the same as M2M account names.
    # M2M account names are typically "NNNNNNNNNN-NNNNN" format.
    VERIZON_THINGSPACE_M2M_ACCOUNT_ID: str = ""
    # Session login endpoint path for obtaining VZ-M2M-Token session GUID
    VERIZON_THINGSPACE_M2M_SESSION_LOGIN_PATH: str = "/ts/v1/session/login"
    # legacy_short_key_secret
    VERIZON_THINGSPACE_SHORT_KEY: str = ""
    VERIZON_THINGSPACE_SHORT_SECRET: str = ""
    # username_password_session
    VERIZON_THINGSPACE_USERNAME: str = ""
    VERIZON_THINGSPACE_PASSWORD: str = ""

    # ── Telnyx (SIP trunking — webhooks, CDR ingestion) ────────────────
    # Ed25519 public key from the Telnyx portal.  When set, inbound
    # Telnyx webhook signatures are verified; when empty, verification
    # is skipped (pre-Phase-3 behavior).
    TELNYX_PUBLIC_KEY: str = ""
    # Outbound Telnyx API key — reserved for later use (DID / E911 / SIM
    # operations, live line registration status).  Not used by the
    # webhook / CDR ingestion path.
    TELNYX_API_KEY: str = ""

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

    @cached_property
    def internal_tenant_id_set(self) -> set[str]:
        """Parsed INTERNAL_TENANT_IDS, ready for membership checks."""
        return {t.strip() for t in self.INTERNAL_TENANT_IDS.split(",") if t.strip()}


settings = Settings()
