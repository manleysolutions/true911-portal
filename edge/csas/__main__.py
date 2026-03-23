"""Standalone smoke-test runner for the CSAS True911 client.

Usage:
    DEVICE_ID=CSAS-001 DEVICE_API_KEY=t91_abc123 TRUE911_BASE_URL=https://true911-api.onrender.com \
        python -m edge.csas

Sends one heartbeat and one observation, then exits.
"""

import logging
import sys

from . import config
from .true911_client import True911Client

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("csas")


def main() -> int:
    if not config.DEVICE_ID or not config.DEVICE_API_KEY:
        logger.error(
            "DEVICE_ID and DEVICE_API_KEY must be set. "
            "Export them as environment variables."
        )
        return 1

    client = True911Client()

    logger.info(
        "Connecting to %s as device %s",
        client.base_url,
        client.device_id,
    )

    # ── Heartbeat ─────────────────────────────────────────────────
    hb = client.send_heartbeat(
        status="running",
        uptime=120,
        version="0.1.0",
        extra={"signal_dbm": -75, "sip_status": "registered"},
    )
    if hb:
        logger.info("Heartbeat accepted — next in %ss", hb.get("next_heartbeat_seconds"))
    else:
        logger.warning("Heartbeat rejected or unreachable")

    # ── Observation ───────────────────────────────────────────────
    obs = client.send_observation(
        line_id="line-smoke-test",
        port_index=0,
        dtmf_digits="*1234567890#",
        voice_energy_estimate=0.05,
        silence_ratio=0.85,
    )
    if obs:
        cls = obs.get("classification", {})
        logger.info(
            "Classification: %s (confidence=%.2f)",
            cls.get("line_type", "?"),
            cls.get("confidence_score", 0),
        )
    else:
        logger.warning("Observation rejected or unreachable")

    return 0


sys.exit(main())
