"""Asset liveness audit by MSISDN (READ-ONLY).

For each MSISDN, gathers the True911 device / line / site / customer plus
liveness signals (heartbeat, network event, call activity, telemetry, alerts,
E911) and recommends a disposition: active / inactive / orphaned / unknown.
Answers "is this asset genuinely in use, or a historical record to retire?".

Strictly READ-ONLY: only SELECTs; no writes, no status/customer changes, no
migrations. Optional activity sources (calls/telemetry/incidents/notifications)
are queried best-effort — a missing/renamed table degrades that field to "n/a"
rather than failing the report. ``--export-json`` writes an operator artifact.

Run:
    python -m app.audit_asset_liveness \
        --msisdn 7869600498 --msisdn 7869600490 --msisdn 7869600588 --msisdn 7869600567
    python -m app.audit_asset_liveness --export-json webber_assets.json
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# The 4 Webber MSISDNs are the default subjects.
DEFAULT_MSISDNS = ["7869600498", "7869600490", "7869600588", "7869600567"]
ACTIVE_DAYS = 30
_ACTIVE_STATES = frozenset({"active", "provisioning"})


# ── pure helpers (unit-tested, no DB) ────────────────────────────────────
def msisdn_variants(m) -> list[str]:
    """Equivalent MSISDN spellings for an IN-list match (10-digit, 1+10, E.164)."""
    digits = "".join(c for c in str(m or "") if c.isdigit())
    if not digits:
        return []
    core = digits[-10:] if len(digits) >= 10 else digits
    out = {str(m), digits, core, "1" + core, "+1" + core, "+" + digits}
    return sorted(v for v in out if v)


def _aware(dt):
    if dt is None or not isinstance(dt, _dt.datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=_dt.timezone.utc)


def _most_recent(*dts):
    vals = [d for d in (_aware(x) for x in dts) if d is not None]
    return max(vals) if vals else None


def classify_disposition(asset: dict, *, now: _dt.datetime,
                         active_days: int = ACTIVE_DAYS) -> str:
    """Recommend a disposition for one asset. Pure.

      unknown  — no device and no line found for the MSISDN.
      orphaned — a device/line exists but has no customer owner.
      active   — owned AND a liveness signal within ``active_days`` AND a status
                 that is active/provisioning.
      inactive — owned but stale / no recent liveness (a historical record).
    """
    if not asset.get("device_id") and not asset.get("line_id"):
        return "unknown"
    if asset.get("customer_id") is None:
        return "orphaned"
    last = _most_recent(asset.get("last_heartbeat"), asset.get("last_network_event"),
                        asset.get("last_call_at"), asset.get("last_telemetry_at"))
    status_active = ((asset.get("device_status") or "").strip().lower() in _ACTIVE_STATES
                     or (asset.get("line_status") or "").strip().lower() in _ACTIVE_STATES)
    if last is not None and (now - last).days <= active_days and status_active:
        return "active"
    return "inactive"


def disposition_reason(asset: dict, disposition: str, *, now: _dt.datetime) -> str:
    last = _most_recent(asset.get("last_heartbeat"), asset.get("last_network_event"),
                        asset.get("last_call_at"), asset.get("last_telemetry_at"))
    age = f"{(now - last).days}d ago" if last else "never"
    if disposition == "unknown":
        return "no True911 device or line carries this MSISDN"
    if disposition == "orphaned":
        return "device/line exists but no customer owner — dangling record"
    if disposition == "active":
        return f"recent liveness ({age}) + active status"
    return f"owned but stale (last liveness {age}) — historical / retire candidate"


# ── DB load (READ-ONLY, best-effort for optional activity tables) ────────
async def _max_dt(db, sql: str, params: dict):
    """Best-effort scalar datetime; returns None if the table/column is absent."""
    from sqlalchemy import text
    try:
        return (await db.execute(text(sql), params)).scalar()
    except Exception:
        return None


async def gather_asset(db, msisdn: str) -> dict:
    from sqlalchemy import select, text
    from app.models.device import Device
    from app.models.line import Line
    from app.models.site import Site
    from app.models.customer import Customer

    variants = msisdn_variants(msisdn)
    devices = (await db.execute(select(Device).where(Device.msisdn.in_(variants)))).scalars().all() if variants else []
    lines = (await db.execute(select(Line).where(Line.did.in_(variants)))).scalars().all() if variants else []

    dev = devices[0] if devices else None
    ln = lines[0] if lines else None
    site_id = (dev.site_id if dev else None) or (ln.site_id if ln else None)
    site = (await db.execute(select(Site).where(Site.site_id == site_id))).scalar_one_or_none() if site_id else None
    customer_id = (ln.customer_id if ln and ln.customer_id else None) or (site.customer_id if site else None)
    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none() if customer_id else None

    dev_ids = [d.device_id for d in devices]
    line_ids = [l.line_id for l in lines]
    site_ids = [site_id] if site_id else []

    # Best-effort activity signals.
    last_call = await _max_dt(
        db,
        "SELECT max(started_at) FROM call_records WHERE "
        "(device_id = ANY(:dev)) OR (line_id = ANY(:lns)) OR (did = ANY(:var)) "
        "OR (from_number = ANY(:var)) OR (to_number = ANY(:var))",
        {"dev": dev_ids or [""], "lns": line_ids or [""], "var": variants or [""]})
    last_telem = await _max_dt(
        db, "SELECT max(recorded_at) FROM command_telemetry WHERE device_id = ANY(:dev)",
        {"dev": dev_ids or [""]})
    open_alerts = await _max_dt(
        db, "SELECT count(*) FROM incidents WHERE site_id = ANY(:s) "
            "AND status NOT IN ('closed','resolved')", {"s": site_ids or [""]}) or 0

    asset = {
        "msisdn": msisdn,
        "device_id": dev.device_id if dev else None,
        "line_id": ln.line_id if ln else None,
        "site_id": site_id,
        "site_name": getattr(site, "site_name", None),
        "customer_id": customer_id,
        "customer_name": getattr(customer, "name", None),
        "customer_status": getattr(customer, "status", None),
        "device_status": getattr(dev, "status", None),
        "line_status": getattr(ln, "status", None),
        "site_status": getattr(site, "status", None),
        "network_status": getattr(dev, "network_status", None),
        "telemetry_source": getattr(dev, "telemetry_source", None),
        "data_usage_mb": getattr(dev, "data_usage_mb", None),
        "last_heartbeat": getattr(dev, "last_heartbeat", None),
        "last_network_event": getattr(dev, "last_network_event", None),
        "last_status_update": _most_recent(getattr(dev, "updated_at", None),
                                           getattr(ln, "updated_at", None)),
        "last_call_at": last_call,
        "last_telemetry_at": last_telem,
        "open_alert_count": int(open_alerts or 0),
        "e911_status": getattr(site, "e911_status", None) or getattr(ln, "e911_status", None),
        "e911_location": _fmt_e911(site, ln),
        "device_count": len(devices),
        "line_count": len(lines),
    }
    return asset


def _fmt_e911(site, ln) -> Optional[str]:
    def parts(o):
        return ", ".join(str(x) for x in (
            getattr(o, "e911_street", None), getattr(o, "e911_city", None),
            getattr(o, "e911_state", None), getattr(o, "e911_zip", None)) if x)
    for o in (site, ln):
        if o is not None:
            p = parts(o)
            if p:
                return p
    return None


# ── report ───────────────────────────────────────────────────────────────
def _print(rows: list[dict], now: _dt.datetime) -> None:
    print("=" * 80)
    print("Asset Liveness Audit (by MSISDN)  —  READ-ONLY")
    print("=" * 80)
    from collections import Counter
    dispo = Counter()
    for a in rows:
        d = classify_disposition(a, now=now)
        dispo[d] += 1
        print(f"\n• MSISDN {a['msisdn']}  ->  [{d.upper()}]  {disposition_reason(a, d, now=now)}")
        print(f"    device={a['device_id'] or '-'}  line={a['line_id'] or '-'}  "
              f"site={a['site_id'] or '-'} ({a['site_name'] or '-'})")
        print(f"    customer={a['customer_id'] or '-'} ({a['customer_name'] or '-'})  "
              f"cust_status={a['customer_status'] or '-'}")
        print(f"    status: device={a['device_status'] or '-'} line={a['line_status'] or '-'} "
              f"site={a['site_status'] or '-'} network={a['network_status'] or '-'}")
        print(f"    last_heartbeat={a['last_heartbeat']}  last_network_event={a['last_network_event']}")
        print(f"    last_status_update={a['last_status_update']}  last_call={a['last_call_at']}  "
              f"last_telemetry={a['last_telemetry_at']}")
        print(f"    open_alerts={a['open_alert_count']}  telemetry_source={a['telemetry_source'] or '-'}  "
              f"data_usage_mb={a['data_usage_mb']}")
        print(f"    e911={a['e911_status'] or '-'}  loc={a['e911_location'] or '-'}")
        if a["device_count"] > 1 or a["line_count"] > 1:
            print(f"    NOTE: MSISDN maps to {a['device_count']} devices / {a['line_count']} lines (duplicate)")
    print("\n--- DISPOSITION SUMMARY ---")
    for k in ("active", "inactive", "orphaned", "unknown"):
        print(f"  {k:<10}: {dispo.get(k, 0)}")
    print("\n  (Read-only — no writes, no status/customer changes.)")


def to_report(rows: list[dict], now: _dt.datetime) -> dict:
    out = []
    for a in rows:
        d = classify_disposition(a, now=now)
        out.append({**a, "disposition": d, "disposition_reason": disposition_reason(a, d, now=now)})
    from collections import Counter
    summary = dict(Counter(r["disposition"] for r in out))
    return {"read_only": True, "summary": summary, "assets": out}


async def run(msisdns: list[str], *, export_json: Optional[str] = None) -> dict:
    from app.database import AsyncSessionLocal
    now = _dt.datetime.now(_dt.timezone.utc)
    async with AsyncSessionLocal() as db:
        rows = [await gather_asset(db, m) for m in msisdns]
    _print(rows, now)
    if export_json:
        with open(export_json, "w", encoding="utf-8") as fh:
            json.dump(to_report(rows, now), fh, indent=2, ensure_ascii=False, default=str)
        print(f"\n  Wrote JSON -> {export_json}")
    return to_report(rows, now)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only asset liveness audit by MSISDN.")
    parser.add_argument("--msisdn", action="append", default=[], help="MSISDN (repeatable)")
    parser.add_argument("--export-json", dest="export_json", help="write JSON report")
    args = parser.parse_args()
    msisdns = args.msisdn or DEFAULT_MSISDNS
    try:
        asyncio.run(run(msisdns, export_json=args.export_json))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: audit aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
