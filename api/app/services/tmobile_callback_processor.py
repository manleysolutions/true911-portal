"""Process an archived T-Mobile PIT callback payload.

Invoked by ``app.services.sim_service.handle_webhook`` ONLY when both
conditions hold:

  * ``settings.FEATURE_TMOBILE_CALLBACK_INGEST`` is exactly ``"true"``
    (post strip+lower), AND
  * the worker job's ``source`` is ``"tmobile"``.

Off-path callers see the unchanged stub behavior in ``handle_webhook``.

What this module does:

  1. Loads the ``IntegrationPayload`` written by the callback router.
  2. Marks the payload ``processed=True`` defensively, even on
     skip paths — every callback should be auditable as "we saw it".
  3. Extracts ICCID, MSISDN, network_status, event_timestamp, and
     event_type from the payload (body + synthesized headers).
  4. Refuses promotion if:
       * no ICCID and no MSISDN are present (no way to match),
       * the event timestamp is older than
         ``settings.TMOBILE_CALLBACK_MAX_AGE_SECONDS`` (replay guard),
       * the MSISDN-only match returns more than one ``Sim`` row
         (ambiguous — we will not guess),
       * the matched ``Sim`` has no linked ``Device``.
  5. On a single safe match with a linked device, reuses
     :func:`app.services.carrier_adapter.ingest_carrier_telemetry`
     to write ``device.last_network_event = now`` (the field the
     Health Normalizer reads as ``last_carrier_event_at``) plus a
     ``CommandTelemetry`` row — the same path Verizon already uses.

What this module deliberately does NOT do:

  * Outbound TAAP call (Phase 2 — separate flag).
  * Signature verification (still pending T-Mobile spec — known gap).
  * Tenant guessing (ICCID is globally unique per
    ``Sim.iccid unique=True``, so a single match implicitly
    identifies the tenant).
  * Provisioning writes (never create SIM, never create Device).
  * E911 / call routing / customer record updates.
  * Idempotency tracking (deferred; same payload twice is OK — the
    write is effectively idempotent because both calls set
    ``last_network_event = now`` to ~the same value).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.device import Device
from app.models.integration_payload import IntegrationPayload
from app.models.sim import Sim
from app.services.carrier_adapter import CarrierTelemetry, ingest_carrier_telemetry

logger = logging.getLogger("true911.tmobile.callback_processor")


# Synthetic header the callback router writes at archive time so the
# worker can recover the URL-path event type without parsing the URL.
EVENT_TYPE_HEADER = "x-true911-tmobile-event-type"

# Body field aliases — callbacks across event types use different
# casings + alternate names.  Order matters: first hit wins.
_ICCID_KEYS = ("iccid", "ICCID", "sim_iccid", "simIccid")
_MSISDN_KEYS = ("msisdn", "MSISDN", "subscriber", "mdn", "phone_number")
_NETWORK_STATUS_KEYS = (
    "network_status",
    "networkStatus",
    "registration_status",
    "registrationStatus",
    "status",
)
_TIMESTAMP_KEYS = (
    "event_time",
    "eventTime",
    "timestamp",
    "occurred_at",
    "occurredAt",
)


# ─── Public types ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ExtractedSignal:
    """Everything pulled out of a callback body + headers, plus
    fallbacks.  Both identifier fields may be ``None`` — callers
    must treat that case as 'archive only, no promotion'.
    """

    iccid: Optional[str]
    msisdn: Optional[str]
    network_status: Optional[str]
    event_timestamp: datetime  # always populated (falls back to received_at)
    event_type: str  # "provisioning" | "usage" | "device_change" | ... | "unknown"


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of one payload processing.  ``status`` is one of:

      ``promoted``               — Device.last_network_event updated
      ``skipped:no_identifier``  — body had no ICCID and no MSISDN
      ``skipped:no_match``       — identifier didn't match any Sim
      ``skipped:ambiguous_match``— MSISDN matched multiple Sim rows
      ``skipped:no_device``      — Sim matched but no linked Device
      ``skipped:replay``         — event_timestamp older than cap
      ``error:malformed``        — body could not be parsed
      ``error:not_found``        — payload_id did not resolve
    """

    status: str
    reason: Optional[str] = None
    matched_sim_iccid: Optional[str] = None
    matched_device_id: Optional[str] = None


# ─── Extraction ────────────────────────────────────────────────────


def _first_present(body: dict, keys: tuple[str, ...]) -> Optional[str]:
    """Return the first non-empty value among ``keys`` in ``body``."""
    for k in keys:
        if k in body and body[k] not in (None, ""):
            return str(body[k]).strip()
    return None


def _parse_event_timestamp(body: dict, fallback: datetime) -> datetime:
    """Parse a timestamp out of the body using ISO-8601 or epoch.

    Returns ``fallback`` (typically ``IntegrationPayload.created_at``)
    when no parseable timestamp is present.
    """
    for k in _TIMESTAMP_KEYS:
        if k not in body or body[k] in (None, ""):
            continue
        raw = body[k]
        # ISO 8601 string (with or without trailing 'Z')
        if isinstance(raw, str):
            try:
                # Python's fromisoformat doesn't accept 'Z' until 3.11
                ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                return ts
            except ValueError:
                pass
        # epoch seconds (int or float)
        if isinstance(raw, (int, float)):
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                pass
    return fallback


def extract_signal(
    payload: IntegrationPayload,
) -> ExtractedSignal:
    """Pull identifiers + status + timestamp out of an archived payload.

    Tolerant of malformed bodies — returns an ``ExtractedSignal`` with
    ``iccid=None`` and ``msisdn=None`` rather than raising, because the
    caller's appropriate action ("archive only, no promotion") is the
    same whether the body is empty, malformed, or simply missing
    identifiers.
    """
    headers = payload.headers or {}
    event_type = str(headers.get(EVENT_TYPE_HEADER) or "unknown").strip().lower() or "unknown"

    # IntegrationPayload.body is JSONB (dict) when JSON-parseable,
    # else None with raw_body retained.  We only extract from parsed.
    body: dict
    raw_body = payload.body
    if isinstance(raw_body, dict):
        body = raw_body
    elif isinstance(raw_body, str):
        # Defensive — shouldn't happen given the archiver writes dict.
        try:
            body = json.loads(raw_body)
            if not isinstance(body, dict):
                body = {}
        except (json.JSONDecodeError, ValueError):
            body = {}
    else:
        body = {}

    created_at = payload.created_at
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    elif created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return ExtractedSignal(
        iccid=_first_present(body, _ICCID_KEYS),
        msisdn=_first_present(body, _MSISDN_KEYS),
        network_status=_first_present(body, _NETWORK_STATUS_KEYS),
        event_timestamp=_parse_event_timestamp(body, created_at),
        event_type=event_type,
    )


# ─── SIM matching ──────────────────────────────────────────────────


@dataclass(frozen=True)
class SimMatchResult:
    kind: str  # "one" | "none" | "ambiguous"
    sim: Optional[Sim] = None
    candidate_count: int = 0


async def match_sim(db: AsyncSession, signal: ExtractedSignal) -> SimMatchResult:
    """Look up the Sim that this callback is about.

    Tenant scoping is implicit: ``Sim.iccid`` has a global UNIQUE
    constraint per the schema, so a successful ICCID match returns
    a single row whose ``tenant_id`` IS the tenant context.  No
    cross-tenant lookup happens.

    Fallback to MSISDN is used only when ICCID is absent — and
    MSISDN matches are explicitly refused when more than one row
    is returned.
    """
    # ICCID is globally unique — try it first.  Even though we don't
    # have a tenant up-front, the unique constraint guarantees this
    # returns 0 or 1 row, so the answer is unambiguous.
    if signal.iccid:
        q = select(Sim).where(Sim.iccid == signal.iccid)
        row = (await db.execute(q)).scalar_one_or_none()
        if row is not None:
            return SimMatchResult(kind="one", sim=row, candidate_count=1)
        # ICCID was given but didn't match — fall through to MSISDN.

    if signal.msisdn:
        # MSISDN is NOT unique.  Count first, then load if exactly one.
        count_q = select(func.count(Sim.id)).where(Sim.msisdn == signal.msisdn)
        count = int((await db.execute(count_q)).scalar() or 0)
        if count == 0:
            return SimMatchResult(kind="none", candidate_count=0)
        if count > 1:
            # Refuse to guess.
            return SimMatchResult(kind="ambiguous", candidate_count=count)
        load_q = select(Sim).where(Sim.msisdn == signal.msisdn)
        row = (await db.execute(load_q)).scalar_one_or_none()
        if row is not None:
            return SimMatchResult(kind="one", sim=row, candidate_count=1)

    return SimMatchResult(kind="none", candidate_count=0)


async def find_linked_device(db: AsyncSession, sim: Sim) -> Optional[Device]:
    """Resolve the Device for a matched Sim, tenant-scoped.

    Uses ``Sim.device_id`` (the direct String linkage) rather than
    the DeviceSim junction — both exist in the schema, but the direct
    column is what carrier sync paths populate.  Returns ``None`` if
    the Sim isn't assigned to a Device or the linked Device row is
    missing for any reason (e.g. it was decommissioned).
    """
    if not sim.device_id:
        return None
    q = select(Device).where(
        Device.tenant_id == sim.tenant_id,
        Device.device_id == sim.device_id,
    )
    return (await db.execute(q)).scalar_one_or_none()


# ─── Orchestrator ──────────────────────────────────────────────────


async def process_payload(db: AsyncSession, payload_id: str) -> ProcessResult:
    """Drive the full archive → extract → match → promote flow.

    Never raises an upstream error — every failure path returns a
    ``ProcessResult`` with a ``status`` that the caller can log and
    continue.  The IntegrationPayload row is always marked processed
    (when found) so retries don't pile up.

    The function commits its own DB writes (one transaction) so the
    caller's responsibility is just to invoke and log.
    """
    payload = await _load_payload(db, payload_id)
    if payload is None:
        logger.warning("T-Mobile callback %s: IntegrationPayload not found", payload_id)
        return ProcessResult(status="error:not_found")

    # Mark processed defensively, even on every skip/error path below.
    payload.processed = True

    try:
        signal = extract_signal(payload)
    except Exception as exc:  # noqa: BLE001 — extraction is supposed to be tolerant
        logger.warning(
            "T-Mobile callback %s: extraction failed unexpectedly (%s: %s)",
            payload_id, type(exc).__name__, exc,
        )
        await db.commit()
        return ProcessResult(status="error:malformed", reason=str(exc))

    if not signal.iccid and not signal.msisdn:
        logger.info(
            "T-Mobile callback %s: no ICCID/MSISDN in body — archive only "
            "(event_type=%s)",
            payload_id, signal.event_type,
        )
        await db.commit()
        return ProcessResult(status="skipped:no_identifier")

    # Replay guard.  Always uses UTC-aware comparison.
    now = datetime.now(timezone.utc)
    age_seconds = (now - signal.event_timestamp).total_seconds()
    if age_seconds > settings.TMOBILE_CALLBACK_MAX_AGE_SECONDS:
        logger.warning(
            "T-Mobile callback %s: event timestamp %ds old, skipping "
            "promotion (cap=%ds, event_type=%s)",
            payload_id, int(age_seconds),
            settings.TMOBILE_CALLBACK_MAX_AGE_SECONDS, signal.event_type,
        )
        await db.commit()
        return ProcessResult(status="skipped:replay", reason=f"age={int(age_seconds)}s")

    match = await match_sim(db, signal)
    if match.kind == "none":
        logger.info(
            "T-Mobile callback %s: no Sim matches iccid=%s msisdn=%s — "
            "archive only (event_type=%s)",
            payload_id,
            _redact_identifier(signal.iccid),
            _redact_identifier(signal.msisdn),
            signal.event_type,
        )
        await db.commit()
        return ProcessResult(status="skipped:no_match")
    if match.kind == "ambiguous":
        logger.warning(
            "T-Mobile callback %s: AMBIGUOUS Sim match on msisdn=%s "
            "(%d candidates) — refusing to guess, archive only "
            "(event_type=%s)",
            payload_id,
            _redact_identifier(signal.msisdn),
            match.candidate_count,
            signal.event_type,
        )
        await db.commit()
        return ProcessResult(
            status="skipped:ambiguous_match",
            reason=f"candidates={match.candidate_count}",
        )

    sim = match.sim
    assert sim is not None  # mypy aid

    device = await find_linked_device(db, sim)
    if device is None:
        logger.info(
            "T-Mobile callback %s: Sim matched (iccid=%s tenant=%s) but "
            "no linked Device — archive only (event_type=%s)",
            payload_id,
            _redact_identifier(sim.iccid),
            sim.tenant_id,
            signal.event_type,
        )
        await db.commit()
        return ProcessResult(
            status="skipped:no_device",
            matched_sim_iccid=sim.iccid,
        )

    # Single safe match with linked device → promote via the existing
    # carrier_adapter pipeline.  This is identical to the path Verizon
    # uses, so the Health Normalizer will see it through the same
    # last_network_event channel without any normalizer change.
    telemetry = CarrierTelemetry(
        device_id=device.device_id,
        carrier="t-mobile",
        signal_dbm=None,  # callbacks don't carry signal strength
        network_status=signal.network_status,
        roaming=None,
        data_usage_mb=None,
        network_tech=None,
    )
    await ingest_carrier_telemetry(db, sim.tenant_id, telemetry)
    await db.commit()

    logger.info(
        "T-Mobile callback %s: promoted to carrier liveness "
        "(device=%s tenant=%s event_type=%s network_status=%s)",
        payload_id,
        device.device_id,
        sim.tenant_id,
        signal.event_type,
        signal.network_status or "<none>",
    )
    return ProcessResult(
        status="promoted",
        matched_sim_iccid=sim.iccid,
        matched_device_id=device.device_id,
    )


# ─── Helpers ───────────────────────────────────────────────────────


async def _load_payload(
    db: AsyncSession, payload_id: str
) -> Optional[IntegrationPayload]:
    q = select(IntegrationPayload).where(
        IntegrationPayload.payload_id == payload_id
    )
    return (await db.execute(q)).scalar_one_or_none()


def _redact_identifier(value: Optional[str]) -> str:
    """Render an ICCID/MSISDN for logs without leaking the full value.

    Keeps the first 6 chars (carrier prefix info) and last 2 chars
    (sanity check) and replaces the middle with dots.  Returns
    ``<none>`` for missing values.
    """
    if not value:
        return "<none>"
    if len(value) <= 8:
        return value[0] + "***"
    return f"{value[:6]}...{value[-2:]}"
