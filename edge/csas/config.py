"""CSAS edge-client configuration.

Reads from environment variables with sensible defaults for local dev.
All True911 communication requires DEVICE_ID and DEVICE_API_KEY.
"""

from __future__ import annotations

import os


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ── True911 cloud connection ──────────────────────────────────────
TRUE911_BASE_URL: str = _env("TRUE911_BASE_URL", "http://localhost:8000")

# Device identity — must match a registered device in True911
DEVICE_ID: str = _env("DEVICE_ID", "")
DEVICE_API_KEY: str = _env("DEVICE_API_KEY", "")

# Optional: default site_id sent with observations (can be overridden per-call)
SITE_ID: str = _env("SITE_ID", "")

# ── Timeouts & retry ─────────────────────────────────────────────
REQUEST_TIMEOUT_SECONDS: int = int(_env("REQUEST_TIMEOUT_SECONDS", "10"))
HEARTBEAT_INTERVAL_SECONDS: int = int(_env("HEARTBEAT_INTERVAL_SECONDS", "60"))

# ── Logging ───────────────────────────────────────────────────────
LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")
