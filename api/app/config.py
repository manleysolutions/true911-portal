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

    # ── T-Mobile Callback Authentication (gates INGEST, default OFF) ──
    # App-layer authenticity check for the T-Mobile PIT callback URLs.
    # When "false" (default) the callback endpoints behave exactly as
    # today — no authentication, ingest gated only by
    # FEATURE_TMOBILE_CALLBACK_INGEST.  When "true", a callback may only
    # ARCHIVE + enqueue (i.e. mutate Device state via the worker) if it
    # presents the shared secret AND (when IP enforcement is on) arrives
    # from an allowlisted source.  On a failed check the handler logs a
    # structured WARNING and SKIPS ingest, but STILL returns HTTP 200 —
    # the always-200 PIT-validator contract is preserved end-to-end.
    #
    # This defends the spoofing / false-state-injection vector: without
    # it, anyone who can reach the URL could promote a stale/forged
    # network event and make an offline life-safety line read CONNECTED.
    # GET reachability probes are unaffected (they mutate nothing).
    # See docs/TMOBILE_CALLBACK_AUTH.md.
    FEATURE_TMOBILE_CALLBACK_AUTH: str = "false"
    # Shared secret T-Mobile must echo back on every callback, either as
    # the X-True911-Callback-Token header (preferred) or a ?token=...
    # query param embedded in the call-back-location URL we register.
    # Compared in constant time.  Empty while FEATURE_TMOBILE_CALLBACK_AUTH
    # is "true" => fail closed (skip ingest, error log, never 500).
    # Dashboard-managed secret (Render env, sync:false) — never in git.
    TMOBILE_CALLBACK_TOKEN: str = ""
    # When "true" (and FEATURE_TMOBILE_CALLBACK_AUTH is on), additionally
    # require the CF-Connecting-IP to fall inside TMOBILE_CALLBACK_SOURCE_IPS
    # before ingesting — defense-in-depth on top of the token.  When
    # "false" (default) the token alone authenticates; the existing
    # passive FEATURE_TMOBILE_CALLBACK_IP_AUDIT logging is unaffected.
    TMOBILE_CALLBACK_IP_ENFORCE: str = "false"

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

    # ── Assurance Engine (MVP — read-only customer assurance label) ──
    # When "false" (default) the /api/assurance/* routes return 404 and the
    # platform behaves exactly as before.  When "true" the read-only Assurance
    # Engine composes operational / commercial-lifecycle / deployment-lifecycle /
    # E911 axes into one customer-facing label (Protected / Attention Needed /
    # Critical / Inactive-Deactivated / Pending Install / Unknown).  It NEVER
    # writes and never overwrites any source-of-truth axis.  See
    # docs/ASSURANCE_ENGINE.md.
    FEATURE_ASSURANCE_ENGINE: str = "false"

    # ── Customer API namespace (RH Go-Live Phase 3) ───────────────
    # Two-key gate for /api/customer/*: a global kill-switch plus a per-tenant
    # allowlist.  Default OFF everywhere; a customer route 404s unless BOTH
    # FEATURE_CUSTOMER_API == "true" AND the caller's tenant_id is listed in
    # CUSTOMER_API_TENANT_ALLOWLIST.  Enabling for RH is a Phase-4 ops action.
    FEATURE_CUSTOMER_API: str = "false"
    CUSTOMER_API_TENANT_ALLOWLIST: str = ""

    # ── Customer preview mode (RH urgent go-live login preview) ────
    # Two-key gate, mirroring the customer API.  When ON for a tenant, the
    # customer OPERATIONAL axis (location / service / equipment protection +
    # equipment health) is presented as Active/Protected — so a customer can be
    # given a login immediately, before live carrier/vendor telemetry is
    # connected.  It is PRESENTATION-ONLY: it never writes or mutates any raw
    # Device/Site/API state, and internal / admin / assurance views read the
    # real state and are unaffected.  The E911 axis is EXCLUDED — emergency
    # addresses stay derived from real stored data (never forced "Verified").
    # Default OFF everywhere.  Rollback: flip FEATURE_CUSTOMER_PREVIEW=false or
    # drop the tenant from CUSTOMER_PREVIEW_TENANT_ALLOWLIST — instant, no
    # deploy, no data change.  See docs/CUSTOMER_EXPERIENCE_BOUNDARY.md.
    FEATURE_CUSTOMER_PREVIEW: str = "false"
    CUSTOMER_PREVIEW_TENANT_ALLOWLIST: str = ""

    # ── Customer Portfolio Registry read model ─────────────────────
    # When enabled (two-key: FEATURE_CUSTOMER_PORTFOLIO_REGISTRY == "true" AND the
    # caller's tenant in CUSTOMER_PORTFOLIO_REGISTRY_TENANT_ALLOWLIST), the customer
    # dashboard + Location/Building Workspace render from the approved Portfolio
    # Registry (canonical PortfolioBuildings) instead of raw Site rows.  READ-ONLY:
    # it never writes the registry or any source, never auto-creates Sites, never
    # marks E911 verified.  If the registry has no visible buildings yet it falls
    # back to the legacy Site path (customer sees no fallback language).  Default OFF.
    FEATURE_CUSTOMER_PORTFOLIO_REGISTRY: str = "false"
    CUSTOMER_PORTFOLIO_REGISTRY_TENANT_ALLOWLIST: str = ""
    # Show high-confidence, customer-safe PENDING (unapproved) buildings to the
    # customer.  Default false — customers see approved buildings only.
    CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS: str = "false"
    # Internal RH pre-go-live preview: an allowlisted tenant's test user previews ALL
    # buildings (approved + pending) so operators can validate before approval.
    CUSTOMER_PORTFOLIO_PREVIEW_PENDING: str = "false"
    CUSTOMER_PORTFOLIO_PREVIEW_TENANT_ALLOWLIST: str = ""

    # ── AI Customer Operations Center / Support Center ─────────────
    # Caller-facing Tier-1 support workflow: identifier lookup → SMS-OTP
    # caller verification → temporary support session → triage → human
    # handoff.  Distinct from the internal AI Support Assistant
    # (/api/support) which serves authenticated users.  When "false"
    # (default) every /api/ops-center route returns 404 and no asset
    # lookup, OTP, or session can be created — the platform behaves
    # exactly as before.  See docs/AI_CUSTOMER_OPERATIONS_CENTER.md.
    FEATURE_OPS_CENTER: str = "false"
    # OTP delivery provider.  "stub" (default) records the challenge and
    # reports success WITHOUT sending anything (safe for dev/CI).
    # "console" additionally logs the code to the server log (dev only —
    # never enable in an internet-exposed environment).  "twilio" and
    # "telnyx" are reserved for Phase 3+ real providers (not yet wired).
    OPS_CENTER_OTP_PROVIDER: str = "stub"  # stub | console | twilio | telnyx
    OPS_CENTER_OTP_CODE_LENGTH: int = 6
    OPS_CENTER_OTP_TTL_SECONDS: int = 300  # OTP validity window
    OPS_CENTER_OTP_MAX_ATTEMPTS: int = 5   # wrong-code attempts before lockout
    # Default escalation / human-handoff phone number used when a session
    # cannot be resolved by the workflow.  Empty = no default; the
    # escalate endpoint then records the handoff without a routing number.
    OPS_CENTER_HANDOFF_NUMBER: str = ""

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

    # ── Zoho Subscription Lifecycle Ingest (staging, default OFF) ───────
    # Makes Zoho CRM the System of Record for LIFECYCLE status (Active /
    # Suspended / Deactivated / Pending Install) — a SEPARATE axis from
    # operational status (Online / Offline / Attention), which stays owned by
    # True911 telemetry / the Health Normalizer.  These flags NEVER cause a
    # write to sites.status / devices.status / lines.status; all Zoho data
    # lands in additive staging tables (zoho_subscription_records,
    # external_record_map, zoho_payload_observations) read by the read-only
    # review surface.  Promotion to an additive lifecycle_status is a separate,
    # later, explicitly-gated phase.  See the Zoho lifecycle plan doc.
    #
    # When "false" (default) a Zoho Subscription_Mgmt webhook behaves exactly as
    # today (archived as an IntegrationEvent, marked needs_mapping, no staging).
    # When "true" the worker additionally upserts the staging record and records
    # a sanitized payload observation.  The webhook auth path is untouched.
    FEATURE_ZOHO_SUBSCRIPTION_INGEST: str = "false"
    # When "true" the ingest populates zoho_subscription_records.lifecycle_state
    # from the status normalizer (Zoho "De-activated" -> deactivated/inactive,
    # never "healthy active monitoring").  When "false" the raw status is still
    # stored but lifecycle_state stays NULL.
    FEATURE_ZOHO_STATUS_NORMALIZER: str = "false"
    # Routing is intentionally configurable because the Zoho webhook field
    # mapping is NOT finalized — a Subscription_Mgmt event is matched when the
    # payload's `module` is in ZOHO_SUBSCRIPTION_MODULES OR its `event_type` is
    # in ZOHO_SUBSCRIPTION_EVENT_TYPES (both comma-separated, case-insensitive).
    # Adjust via env (Render) as Zoho workflows evolve — no code change/deploy.
    ZOHO_SUBSCRIPTION_MODULES: str = "Subscription_Mgmt"
    ZOHO_SUBSCRIPTION_EVENT_TYPES: str = ""
    # ── Zoho Subscription_Mgmt staging BACKFILL (pull, default OFF) ─────
    # One-time/maintenance backfill that PULLS Subscription_Mgmt records from
    # the Zoho CRM API and stages them into zoho_subscription_records +
    # external_record_map (the same additive shadow tables the webhook ingest
    # writes).  Needed because the mirror only captures records that arrive via
    # webhook AFTER the flag was enabled — pre-existing Zoho records (e.g. Webber)
    # are absent.  The backfill is dry-run-first and writes NOTHING to
    # sites/devices/lines/customers; it NEVER deletes.  This flag must be "true"
    # for the backfill's APPLY (write) path; dry-run never consults it and never
    # writes.  Idempotent by (org_id, subscription_mgmt_id).
    FEATURE_ZOHO_BACKFILL: str = "false"
    # Stable org_id the backfill keys staging rows on. Should match the webhook's
    # org_id so backfilled and webhook rows reconcile to the same staging row
    # (the unique key is (org_id, subscription_mgmt_id)). Falls back to
    # ZOHO_CRM_ORG_ID, then "zoho_crm".
    ZOHO_BACKFILL_ORG_ID: str = ""
    # ── Device site correction (gated WRITE, default OFF) ──────────────
    # The device→site correction planner (app/plan_device_site_correction.py) is
    # dry-run-first: it only WRITES (devices.site_id <- the matching line's
    # site_id) when --apply is passed AND this flag is "true". It corrects
    # bulk-import placeholder site assignments for ONE customer, customer-scoped,
    # updating devices.site_id ONLY — never lines/customers, never deletes, and
    # refusing ambiguous / multi-line / customer-mismatch / no-proposed-site rows.
    FEATURE_DEVICE_SITE_CORRECTION: str = "false"
    # ── Customer retirement (gated WRITE, default OFF) ─────────────────
    # The customer retirement planner (app/plan_customer_retirement.py) is
    # dry-run-first: it only WRITES (customer/site/device/line status +
    # external_record_map.map_status) when --apply is passed AND this flag is
    # "true" AND its hard safety gates pass (Zoho lifecycle De-activated for all
    # the customer's subscriptions, AND no asset shows recent liveness). It is
    # strictly customer-scoped, never deletes, and never touches other customers.
    FEATURE_CUSTOMER_RETIREMENT: str = "false"
    # Comma-separated Zoho field API names the backfill requests on the GET.
    # Zoho CRM v5 requires a `fields` param for custom-module reads. Blank ->
    # the backfill's DEFAULT_FIELDS (id, Account_Name, FacilityName,
    # Mobile_Number, Device_Activation_Status, Subscription_Type,
    # Connection_Type, Monthly_Recurring_Charge, Service_Term_Ends,
    # Modified_Time). Override via env or the --fields CLI flag.
    ZOHO_SUBSCRIPTION_FIELDS: str = ""

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
    # Activation-first flow (T-Mobile generates the account ID on activation):
    # activation passes a nested baseProduct body + ICCID and a call-back-location
    # header; the account ID returns asynchronously via the callback.
    TMOBILE_PRODUCT_ID: str = ""        # legacy flat productId (unused by the nested baseProduct body)
    TMOBILE_MARKET_ZIP: str = ""        # PIT test market ZIP, e.g. 30338 or 30346
    TMOBILE_CALLBACK_LOCATION: str = "" # call-back-location header URL for async activation completion
    # Nested activation payload mapping (T-Mobile Wholesale PIT, REST, sender/partner 128).
    # Each field has a PIT-safe default baked as a module constant in
    # app/integrations/tmobile_taap.py; these env vars override without a code edit.
    TMOBILE_LANGUAGE: str = "ENGL"              # activation "language" field
    TMOBILE_BASE_PRODUCT_ID: str = ""           # baseProduct.baseProductId, e.g. "Infatrac Internet Access Plan"
    TMOBILE_WPS: str = ""                        # baseProduct.wps, e.g. "00011586"
    # HARD live-call switch. Even with valid credentials, activate_subscriber()
    # refuses to send a real PIT activation unless this is explicitly "true".
    # The dry-run preview (build_activation_preview) never consults this flag.
    TMOBILE_PIT_LIVE_CALLS_ENABLED: str = "false"
    # Resource paths are env-driven so a T-Mobile gateway routing change does not
    # require a code edit. The PIT onboarding gateway URL list uses
    # /wholesale/v1/subscriber (NOT the older /wholesale/subscriber/v2).
    TMOBILE_SUBSCRIBER_BASE_PATH: str = "/wholesale/v1/subscriber"
    # Activation route is kept independently overridable so T-Mobile can hand us
    # a route that is NOT derivable from the subscriber base. Blank => the client
    # derives "{TMOBILE_SUBSCRIBER_BASE_PATH}/activate".
    TMOBILE_ACTIVATION_PATH: str = ""
    # ── PIT designated test-SIM allowlists ──────────────────────────────
    # Three nested tiers gating which ICCIDs a live PIT call may target.
    # Comma-separated 19-20 digit ICCIDs. ALL EMPTY BY DEFAULT — an empty
    # list refuses every operation at that tier rather than allowing all.
    # No wildcards are accepted; malformed entries raise at parse time.
    #
    # The tiers are enforced as SUBSETS: destructive ⊆ lifecycle ⊆ read-only.
    # An ICCID you may not read is not one you may deactivate. Being on a
    # lower-risk list never authorizes a higher-risk operation.
    #
    # The first successfully activated ICCID is additionally PROTECTED
    # (app/integrations/tmobile_lifecycle.PROTECTED_ICCIDS): it must be
    # nominated to the destructive list separately and explicitly, and the
    # operator tool still requires --confirm-protected. Deactivating it would
    # destroy the only end-to-end evidence the integration works.
    #
    # Never put a production ICCID in any of these. See
    # docs/TMOBILE_PIT_TEST_SIM_POLICY.md.
    TMOBILE_PIT_READONLY_ICCID_ALLOWLIST: str = ""
    TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST: str = ""
    TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST: str = ""
    # ── Partner Foundation ID — CONFIGURATION ONLY, NOT SENT ────────────
    # T-Mobile mentioned a "Partner Foundation ID" while diagnosing the
    # 2026-07-16 GENS-0003 "Invalid partnerID" failure, but has NOT supplied:
    #   1. the value             2. the exact HTTP header name
    #   3. whether it REPLACES partner-id or supplements it
    #   4. whether it applies to OAuth, resource calls, or both
    #   5. whether it is signed (in the PoP ehts) or unsigned
    #   6. whether partner-id=128 remains required alongside it
    #
    # These fields exist so the answer can be wired in and tested in minutes once
    # Aman confirms it. Setting them changes NOTHING today: the client never reads
    # them, and no header is emitted. Guessing the header name or mapping this
    # onto partner-id would burn another live PIT activation on a coin flip —
    # every previous guess in this integration cost a full test cycle.
    # See docs/TMOBILE_PIT_ACTIVATION_PAYLOAD.md § "Partner Foundation ID".
    TMOBILE_PARTNER_FOUNDATION_ID: str = ""
    # The header NAME T-Mobile assigns this value. Blank until confirmed — the
    # client must never invent one.
    TMOBILE_PARTNER_FOUNDATION_HEADER: str = ""

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

    @property
    def customer_api_tenant_id_set(self) -> set[str]:
        """Tenants allowed to reach /api/customer/* (when FEATURE_CUSTOMER_API
        is on).  Plain @property (not cached) so a flag/allowlist change takes
        effect without a process restart."""
        return {
            t.strip()
            for t in self.CUSTOMER_API_TENANT_ALLOWLIST.split(",")
            if t.strip()
        }

    @property
    def customer_preview_tenant_id_set(self) -> set[str]:
        """Tenants for which the customer OPERATIONAL axis is shown as
        Active/Protected in preview (when FEATURE_CUSTOMER_PREVIEW is on).
        Plain @property (not cached) so a flag/allowlist change takes effect
        without a process restart."""
        return {
            t.strip()
            for t in self.CUSTOMER_PREVIEW_TENANT_ALLOWLIST.split(",")
            if t.strip()
        }

    @property
    def customer_portfolio_registry_tenant_id_set(self) -> set[str]:
        """Tenants whose customer view renders from the Portfolio Registry (when
        FEATURE_CUSTOMER_PORTFOLIO_REGISTRY is on)."""
        return {t.strip() for t in self.CUSTOMER_PORTFOLIO_REGISTRY_TENANT_ALLOWLIST.split(",")
                if t.strip()}

    @property
    def customer_portfolio_preview_tenant_id_set(self) -> set[str]:
        """Tenants whose test user may preview ALL (approved + pending) buildings."""
        return {t.strip() for t in self.CUSTOMER_PORTFOLIO_PREVIEW_TENANT_ALLOWLIST.split(",")
                if t.strip()}


settings = Settings()
