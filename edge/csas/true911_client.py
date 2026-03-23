"""True911 cloud client for CSAS edge runtime.

Sends heartbeat/state data and line-intelligence observations to the
True911 API using device-key authentication (``X-Device-Key`` header).

All methods fail gracefully — network errors and non-2xx responses are
logged but never raise, so the CSAS runtime keeps running even when the
cloud is unreachable.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from . import config

logger = logging.getLogger("csas.true911_client")


class True911Client:
    """Thin HTTP client for True911 edge ingestion endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        device_id: str | None = None,
        device_api_key: str | None = None,
        site_id: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or config.TRUE911_BASE_URL).rstrip("/")
        self.device_id = device_id or config.DEVICE_ID
        self.device_api_key = device_api_key or config.DEVICE_API_KEY
        self.site_id = site_id or config.SITE_ID
        self.timeout = timeout or config.REQUEST_TIMEOUT_SECONDS

        if not self.device_id:
            logger.warning("DEVICE_ID is not set — True911 calls will fail")
        if not self.device_api_key:
            logger.warning("DEVICE_API_KEY is not set — True911 calls will fail")

    # ── Internal helpers ──────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "X-Device-Key": self.device_api_key,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict) -> Optional[dict]:
        """POST JSON to True911.  Returns parsed response or None on failure."""
        url = f"{self.base_url}{path}"
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            if resp.status_code < 300:
                logger.info("POST %s → %d", path, resp.status_code)
                return resp.json()
            else:
                logger.warning(
                    "POST %s → %d: %s",
                    path,
                    resp.status_code,
                    resp.text[:200],
                )
                return None
        except requests.RequestException as exc:
            logger.error("POST %s failed: %s", path, exc)
            return None

    # ── Heartbeat ─────────────────────────────────────────────────

    def send_heartbeat(
        self,
        *,
        status: str = "running",
        uptime: int | None = None,
        version: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Optional[dict]:
        """Send a heartbeat to ``POST /api/heartbeat``.

        Parameters
        ----------
        status:
            CSAS runtime state (e.g. "running", "idle", "degraded").
        uptime:
            Seconds since boot.
        version:
            CSAS software version string.
        extra:
            Additional key/value pairs merged into the payload
            (signal_dbm, sip_status, board_temp_c, etc.).

        Returns the True911 response dict or None on failure.
        """
        payload: dict[str, Any] = {
            "device_id": self.device_id,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if uptime is not None:
            payload["uptime"] = uptime
        if version is not None:
            payload["version"] = version
        if extra:
            payload.update(extra)

        return self._post("/api/heartbeat", payload)

    # ── Line Intelligence observation ─────────────────────────────

    def send_observation(
        self,
        *,
        line_id: str,
        port_index: int = 0,
        site_id: str | None = None,
        dtmf_digits: str = "",
        fax_tone_present: bool = False,
        modem_carrier_present: bool = False,
        voice_energy_estimate: float = 0.0,
        silence_ratio: float = 0.0,
        window_duration_ms: int = 5000,
        source: str = "csas",
    ) -> Optional[dict]:
        """Send a line-intelligence observation to
        ``POST /api/line-intelligence/edge-classify``.

        Parameters
        ----------
        line_id:
            Identifier of the phone line observed.
        port_index:
            FXS port index on the device (default 0).
        site_id:
            Override the default site; falls back to ``self.site_id``.
        dtmf_digits:
            Raw DTMF digit string captured during the window.
        fax_tone_present:
            Whether a fax CNG/CED tone was detected.
        modem_carrier_present:
            Whether a modem carrier was detected.
        voice_energy_estimate:
            Normalized voice energy level (0.0–1.0).
        silence_ratio:
            Ratio of silence in the observation window (0.0–1.0).
        window_duration_ms:
            Duration of the observation window in milliseconds.
        source:
            Source label (defaults to "csas").

        Returns the classification decision dict or None on failure.
        """
        payload: dict[str, Any] = {
            "device_id": self.device_id,
            "line_id": line_id,
            "port_index": port_index,
            "dtmf_digits": dtmf_digits,
            "fax_tone_present": fax_tone_present,
            "modem_carrier_present": modem_carrier_present,
            "voice_energy_estimate": voice_energy_estimate,
            "silence_ratio": silence_ratio,
            "window_duration_ms": window_duration_ms,
            "source": source,
        }
        resolved_site = site_id or self.site_id
        if resolved_site:
            payload["site_id"] = resolved_site

        return self._post("/api/line-intelligence/edge-classify", payload)
