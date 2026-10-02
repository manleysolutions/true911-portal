"""Durable public acquisition (D-031, D-032).

Invariant: True911 never tells a prospect "received" until the submission exists
durably in True911.  So:
  1. validate (schemas) and screen (honeypot, rate limit, payload size);
  2. persist + COMMIT the acquisition record;
  3. only then attempt the internal notification — a side effect whose outcome
     is recorded on the row and can never delete or duplicate the lead.

Retries are safe: the client sends an idempotency key; a resubmission with the
same key returns the existing record and does not notify again.

No Zoho / CRM writes here (not authorised yet).  No customer, registry,
canonical or E911 data is touched.  Prospect-provided information is intent,
never deployment or verification truth.
"""
from __future__ import annotations

import html
import json
import logging
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.acquisition import AcquisitionRecord

logger = logging.getLogger("true911.acquisition")

# ── allow-lists (public vocabulary; anything else is dropped) ─────────
SERVICE_INTERESTS = {
    "elevator": "Elevator phones",
    "fire_alarm": "Fire alarm communications",
    "emergency_phone": "Emergency phones / call stations",
    "other": "Other / not sure",
}
NEEDS = {
    "copper_replacement": "Replace copper (POTS) lines",
    "visibility": "Status and visibility across locations",
    "e911_readiness": "E911 readiness",
    "not_sure": "Not sure yet",
}
ENTRY_POINTS = ("quote_form", "assessment_request_form", "registration_wizard")

# ── attribution normalisation ─────────────────────────────────────────
_ATTR_LIMITS = {"landing_path": 300, "referrer": 300, "utm_source": 100, "utm_medium": 100,
                "utm_campaign": 150, "utm_term": 150, "utm_content": 150, "initial_cta": 60}
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _clean(value, limit: int) -> Optional[str]:
    if value is None:
        return None
    s = _CTRL.sub("", str(value)).strip()
    return s[:limit] or None


def normalize_attribution(raw: Optional[dict]) -> dict:
    """Constrain client-supplied provenance.  Never used for security decisions."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for key, limit in _ATTR_LIMITS.items():
        v = _clean(raw.get(key), limit)
        if v is None:
            continue
        if key == "landing_path":
            # same-origin path only; never a full URL or query string
            v = "/" + v.lstrip("/").split("?", 1)[0].split("#", 1)[0]
            v = v[:limit]
        elif key == "referrer":
            parts = urlsplit(v)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                continue
            v = f"{parts.scheme}://{parts.netloc}{parts.path}"[:limit]   # drop query strings
        elif key == "initial_cta":
            v = re.sub(r"[^a-z0-9_.-]", "", v.lower())[:limit] or None
            if not v:
                continue
        out[key] = v
    return out


def allowlisted(values, allowed: dict) -> list[str]:
    seen = []
    for v in values or []:
        k = str(v).strip().lower()
        if k in allowed and k not in seen:
            seen.append(k)
    return seen


# ── abuse controls ────────────────────────────────────────────────────
class RateLimiter:
    """Small in-process sliding-window limiter.

    PROCESS-LOCAL, NOT fleet-wide: counts live in this Python process's memory,
    reset on every deploy/restart, and are not shared between uvicorn workers or
    API instances.  A shared store can replace it without changing callers."""

    def __init__(self, limit: int, window_s: int):
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self):
        with self._lock:
            self._hits.clear()


# 5 public submissions per client per 10 minutes, 30 per day.
SHORT_LIMITER = RateLimiter(5, 600)
DAILY_LIMITER = RateLimiter(30, 86400)
# Resume-token lookups (registration GET) — security readiness finding L4.
LOOKUP_LIMITER = RateLimiter(60, 600)


def client_key(request) -> str:
    """Client address for rate limiting: the FIRST X-Forwarded-For entry, else
    the socket peer.  Only ever used to throttle, never to authenticate.

    KNOWN LIMITATION (docs/ACQUISITION.md §6a, BACKLOG A14): the first entry is
    whatever the client sent, so a determined sender can rotate it.  Honest
    browsers get a correct per-visitor key.  The trustworthy parsing boundary for
    our Cloudflare -> Render load balancer -> app topology is not yet established,
    so this deliberately keeps the #198 behaviour rather than guessing a hop count.
    """
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    host = fwd or (request.client.host if request.client else "") or "unknown"
    return host[:64]


def allow_submission(request) -> bool:
    key = client_key(request)
    return SHORT_LIMITER.allow(key) and DAILY_LIMITER.allow(key)


# ── persistence ───────────────────────────────────────────────────────
def _new_ref() -> str:
    return "ACQ-" + secrets.token_hex(6).upper()


async def get_by_idempotency_key(db: AsyncSession, key: str) -> Optional[AcquisitionRecord]:
    return (await db.execute(select(AcquisitionRecord).where(
        AcquisitionRecord.idempotency_key == key))).scalars().first()


def stage_record(db: AsyncSession, *, kind: str, status: str, entry_point: str,
                 email: str, idempotency_key: str, attribution: Optional[dict] = None,
                 company=None, contact_name=None, phone=None, role=None,
                 num_locations=None, service_interests=None, needs=None,
                 message=None, registration_ref=None) -> AcquisitionRecord:
    """Add one acquisition record to the session WITHOUT committing, so a
    caller can make it part of a larger atomic write (the registration wizard)."""
    attr = normalize_attribution(attribution)
    rec = AcquisitionRecord(
        record_ref=_new_ref(), kind=kind, status=status, entry_point=entry_point,
        email=email.strip().lower(), idempotency_key=idempotency_key,
        company=company, contact_name=contact_name, phone=phone, role=role,
        num_locations=num_locations,
        service_interests=json.dumps(service_interests) if service_interests else None,
        needs=json.dumps(needs) if needs else None,
        message=message, registration_ref=registration_ref,
        notification_status="pending", notification_attempts=0, **attr)
    db.add(rec)
    return rec


async def create_record(db: AsyncSession, *, idempotency_key: str,
                        **fields) -> tuple[AcquisitionRecord, bool]:
    """Persist and COMMIT one acquisition record.  Returns (record, created).
    A repeated idempotency key returns the existing record (created=False)."""
    existing = await get_by_idempotency_key(db, idempotency_key)
    if existing is not None:
        return existing, False
    rec = stage_record(db, idempotency_key=idempotency_key, **fields)
    try:
        await db.commit()
    except IntegrityError:
        # a concurrent retry with the same key won the race: return that row
        await db.rollback()
        again = await get_by_idempotency_key(db, idempotency_key)
        if again is not None:
            return again, False
        raise
    await db.refresh(rec)
    return rec, True


async def stage_registration_status(db: AsyncSession, registration_ref: str,
                                   status: str) -> Optional[AcquisitionRecord]:
    """Move the linked acquisition record forward WITHOUT committing (joins the
    caller's transaction).  Acquisition state only — never a deployment state."""
    rec = (await db.execute(select(AcquisitionRecord).where(
        AcquisitionRecord.registration_ref == registration_ref))).scalars().first()
    if rec is not None and rec.status != status:
        rec.status = status
    return rec


async def set_registration_status(db: AsyncSession, registration_ref: str, status: str) -> None:
    """Committing form of ``stage_registration_status`` (used by conversion)."""
    rec = await stage_registration_status(db, registration_ref, status)
    if rec is not None and db.is_modified(rec):
        await db.commit()


# ── notification (post-persistence side effect) ───────────────────────
def _header_safe(s: str) -> str:
    return re.sub(r"[\r\n]+", " ", s)[:180]


def notification_content(rec: AcquisitionRecord) -> tuple[str, str]:
    """Plain, HTML-escaped notification.  Every value is escaped: no prospect
    input can inject markup or headers."""
    label = {"quote_request": "Quote request", "assessment_request": "Life-Safety Assessment request",
             "assessment": "Life-Safety Assessment submitted"}.get(rec.kind, "Public submission")
    interests = ", ".join(SERVICE_INTERESTS.get(k, k) for k in json.loads(rec.service_interests or "[]"))
    needs = ", ".join(NEEDS.get(k, k) for k in json.loads(rec.needs or "[]"))
    fields = [("Record", rec.record_ref), ("Company", rec.company), ("Name", rec.contact_name),
              ("Email", rec.email), ("Phone", rec.phone), ("Role", rec.role),
              ("Locations", rec.num_locations), ("Services", interests), ("Needs", needs),
              ("Message", rec.message), ("Registration", rec.registration_ref),
              ("Entry point", rec.entry_point), ("Landing path", rec.landing_path),
              ("UTM", " / ".join(x for x in (rec.utm_source, rec.utm_medium, rec.utm_campaign) if x))]
    rows = "".join(
        f"<tr><td style='padding:6px 12px;font-weight:600;color:#0b1f3b'>{html.escape(k)}</td>"
        f"<td style='padding:6px 12px;color:#334155'>{html.escape(str(v))}</td></tr>"
        for k, v in fields if v not in (None, ""))
    body = (f"<html><body style='font-family:sans-serif'><h2 style='color:#0b1f3b'>{html.escape(label)}</h2>"
            f"<p style='color:#475569'>Stored in True911 as {html.escape(rec.record_ref)}. "
            f"Prospect-provided information — not verified.</p>"
            f"<table style='border-collapse:collapse;border:1px solid #e2e8f0'>{rows}</table></body></html>")
    subject = _header_safe(f"True911 {label} — {rec.company or rec.email}")
    return subject, body


async def notify(db: AsyncSession, rec: AcquisitionRecord, *, settings=None, sender=None) -> str:
    """Attempt the internal notification and RECORD the outcome on the row.
    Never raises; never deletes or duplicates the lead.  ``sent`` means only
    that the configured transport accepted the message."""
    if settings is None:
        from app.config import settings as _s
        settings = _s
    if sender is None:
        from app.services.email_service import send_email as sender
    state, error = "failed", None
    try:
        if not (settings.SMTP_HOST or "").strip():
            state = "not_configured"          # send_email would only log; don't call that "sent"
        else:
            subject, body = notification_content(rec)
            ok = await sender(settings.TRUE911_BOOTSTRAP_SUPERADMIN_EMAIL, subject, body, settings=settings)
            state = "sent" if ok else "failed"
            if not ok:
                error = "transport did not accept the message"
    except Exception as exc:                  # noqa: BLE001 — side effect must never escape
        state, error = "failed", type(exc).__name__
    logger.info("acquisition %s notification=%s", rec.record_ref, state)
    try:
        rec.notification_status = state
        rec.notification_attempts = (rec.notification_attempts or 0) + 1
        rec.notification_error = (error or None) and error[:300]
        if state == "sent":
            rec.notified_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception:                         # noqa: BLE001 — the lead is already durable
        logger.exception("acquisition %s: could not record notification outcome", rec.record_ref)
        try:
            await db.rollback()
        except Exception:                     # noqa: BLE001
            pass
    return state


def serialize_receipt(rec: AcquisitionRecord) -> dict:
    """The ONLY shape the public client treats as proof of receipt."""
    return {"received": True, "record_ref": rec.record_ref, "status": rec.status}


def serialize_internal(rec: AcquisitionRecord) -> dict:
    return {
        "record_ref": rec.record_ref, "kind": rec.kind, "status": rec.status,
        "company": rec.company, "contact_name": rec.contact_name, "email": rec.email,
        "phone": rec.phone, "role": rec.role, "num_locations": rec.num_locations,
        "service_interests": json.loads(rec.service_interests or "[]"),
        "needs": json.loads(rec.needs or "[]"), "message": rec.message,
        "registration_ref": rec.registration_ref, "entry_point": rec.entry_point,
        "attribution": {k: getattr(rec, k) for k in _ATTR_LIMITS},
        "notification": {"status": rec.notification_status, "attempts": rec.notification_attempts,
                         "error": rec.notification_error,
                         "notified_at": rec.notified_at.isoformat() if rec.notified_at else None},
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }
