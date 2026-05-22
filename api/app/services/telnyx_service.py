"""Telnyx integration — webhook signature verification and call-event
ingestion into the ``call_records`` (CDR) table.

Everything in this module is config-gated and additive:

  * Signature verification is a no-op when ``TELNYX_PUBLIC_KEY`` is
    unset, so the webhook endpoint behaves exactly as it did before
    Phase 3 until the operator configures the key.
  * Call-event ingestion is best-effort — a malformed body, a
    non-call event, or an unrecognized DID is logged and skipped; it
    never raises into the webhook handler (Telnyx would otherwise
    retry the delivery).

Phase 3 scope is inbound: turning Telnyx ``call.hangup`` events into
CDR rows.  Outbound Telnyx API calls (DID/E911/SIM management, live
line registration status) are intentionally not wired here.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.call_record import CallRecord
from app.models.line import Line

logger = logging.getLogger("true911.telnyx")

# Clock skew tolerated on the webhook timestamp — blunts replay attacks
# without breaking on normal drift between Telnyx and this server.
_SIGNATURE_TOLERANCE_SECONDS = 300

# Telnyx hangup_cause -> call_records.status
_STATUS_BY_HANGUP_CAUSE = {
    "normal_clearing": "completed",
    "user_busy": "busy",
    "no_answer": "no-answer",
    "originator_cancel": "canceled",
    "call_rejected": "failed",
    "unallocated_number": "failed",
}


class TelnyxSignatureError(Exception):
    """Raised when a Telnyx webhook signature fails verification."""


def verify_webhook_signature(
    signature_b64: Optional[str],
    timestamp: Optional[str],
    raw_body: bytes,
) -> None:
    """Verify a Telnyx Ed25519 webhook signature.

    No-op when ``TELNYX_PUBLIC_KEY`` is unset (config-gated — preserves
    the pre-Phase-3 behavior of accepting unsigned webhooks).  When the
    key is configured, raises :class:`TelnyxSignatureError` on any
    verification failure.

    Telnyx signs the bytes ``f"{timestamp}|{raw_body}"`` with Ed25519;
    the base64 signature arrives in the ``telnyx-signature-ed25519``
    header and the unix timestamp in ``telnyx-timestamp``.
    """
    public_key_b64 = settings.TELNYX_PUBLIC_KEY.strip()
    if not public_key_b64:
        return  # verification disabled

    if not signature_b64 or not timestamp:
        raise TelnyxSignatureError("missing Telnyx signature/timestamp headers")

    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        raise TelnyxSignatureError("invalid Telnyx timestamp header")
    age = abs(int(datetime.now(timezone.utc).timestamp()) - ts)
    if age > _SIGNATURE_TOLERANCE_SECONDS:
        raise TelnyxSignatureError(f"Telnyx timestamp outside tolerance ({age}s)")

    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        signed_payload = f"{timestamp}|".encode("utf-8") + raw_body
        public_key.verify(base64.b64decode(signature_b64), signed_payload)
    except InvalidSignature:
        raise TelnyxSignatureError("Telnyx webhook signature mismatch")
    except TelnyxSignatureError:
        raise
    except Exception as exc:  # malformed key or signature encoding
        raise TelnyxSignatureError(f"Telnyx signature verification error: {exc}")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse a Telnyx ISO-8601 timestamp; return None on any failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _normalize_did(value: Optional[str]) -> str:
    """Reduce a phone number to comparable digits (US: drop a leading 1)."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


async def _match_line(db: AsyncSession, did: str) -> Optional[Line]:
    """Find the Line whose DID matches ``did``.

    Exact match first (fast — covers E.164-stored DIDs), then a
    digit-normalized fallback so formatting differences (dashes, a
    leading +1) do not break the association.
    """
    exact = (await db.execute(select(Line).where(Line.did == did))).scalars().first()
    if exact:
        return exact
    target = _normalize_did(did)
    if not target:
        return None
    rows = (await db.execute(select(Line).where(Line.did.isnot(None)))).scalars().all()
    for line in rows:
        if _normalize_did(line.did) == target:
            return line
    return None


async def ingest_call_event(db: AsyncSession, raw_body: bytes) -> Optional[CallRecord]:
    """Parse a Telnyx call webhook and, on ``call.hangup``, write a CDR.

    Best-effort: returns ``None`` (and logs) on any non-fatal condition —
    a non-JSON body, a non-call event, an event other than
    ``call.hangup``, an unrecognized DID, or a duplicate delivery.  The
    CDR is built from ``call.hangup`` because that event carries the
    full call timeline (start / answer / end, hangup cause).
    """
    try:
        event = json.loads(raw_body.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError):
        return None

    data = (event or {}).get("data") or {}
    if data.get("event_type") != "call.hangup":
        return None

    payload = data.get("payload") or {}
    # Idempotency key — prefer the stable per-call session id.
    session_id = (
        payload.get("call_session_id")
        or payload.get("call_leg_id")
        or payload.get("call_control_id")
        or data.get("id")
    )
    if not session_id:
        logger.warning("Telnyx call.hangup with no call identifier — skipped")
        return None
    call_id = f"telnyx-{session_id}"[:64]

    # Telnyx retries webhooks — never insert the same call twice.
    existing = (
        await db.execute(select(CallRecord).where(CallRecord.call_id == call_id))
    ).scalars().first()
    if existing:
        return existing

    direction = (
        "inbound"
        if (payload.get("direction") or "").lower() in ("incoming", "inbound")
        else "outbound"
    )
    from_number = payload.get("from")
    to_number = payload.get("to")
    # The deployment-owned DID is the local leg of the call.
    did = to_number if direction == "inbound" else from_number

    line = await _match_line(db, did) if did else None
    if line is None:
        logger.warning(
            "Telnyx call.hangup for DID %r matched no line — CDR not stored", did,
        )
        return None

    started_at = _parse_dt(payload.get("start_time"))
    answered_at = _parse_dt(payload.get("answer_time"))
    ended_at = _parse_dt(payload.get("end_time"))
    duration = None
    if started_at and ended_at:
        duration = max(0, int((ended_at - started_at).total_seconds()))

    status = _STATUS_BY_HANGUP_CAUSE.get(
        (payload.get("hangup_cause") or "").lower(), "completed",
    )

    record = CallRecord(
        call_id=call_id,
        tenant_id=line.tenant_id,
        customer_id=line.customer_id,
        site_id=line.site_id,
        device_id=line.device_id,
        line_id=line.line_id,
        provider="telnyx",
        direction=direction,
        from_number=from_number,
        to_number=to_number,
        did=line.did,
        status=status,
        started_at=started_at,
        answered_at=answered_at,
        ended_at=ended_at,
        duration_seconds=duration,
        telnyx_call_id=payload.get("call_leg_id") or payload.get("call_control_id"),
        telnyx_cdr_id=data.get("id"),
        metadata_json=json.dumps({
            "event_id": data.get("id"),
            "hangup_cause": payload.get("hangup_cause"),
            "hangup_source": payload.get("hangup_source"),
            "connection_id": payload.get("connection_id"),
        }),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info(
        "Telnyx CDR stored: call_id=%s line=%s tenant=%s status=%s",
        call_id, line.line_id, line.tenant_id, status,
    )
    return record
