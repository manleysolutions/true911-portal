"""Restoration Hardware — device identity DISCOVERY audit (READ-ONLY).

The RH telemetry dry-run showed the real blocker is device identity: most RH
devices are inventory rows with no vendor adapter / no monitorable identity.
This audit explains, per device, exactly what it is and what information is
needed to make it monitorable — turning unknown inventory into an operator
checklist and a mapping template that feeds the PR #81 importer.

NEVER writes — only SELECTs. Does NOT run the identity backfill or telemetry
apply, and never touches another tenant.

Run:
    python -m app.audit_rh_device_identity
    python -m app.audit_rh_device_identity --export /tmp/rh_device_identity_audit.json
    python -m app.audit_rh_device_identity --export /tmp/rh_device_identity_audit.csv
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RH_TENANT = os.environ.get("RH_IDENTITY_TENANT", "restoration-hardware")

# Categories (each device gets exactly one).
MONITORABLE_NOW = "monitorable_now"
AFTER_TMOBILE_ACCOUNT = "monitorable_after_tmobile_account_id"
MANUAL_REQUIRED = "manual_verification_required"
NEEDS_IDENTITY = "needs_identity_mapping"
NEEDS_CREDENTIALS = "needs_vendor_credentials"
UNKNOWN_TYPE = "unknown_device_type"
DATA_CONFLICT = "data_conflict"

CATEGORIES = (MONITORABLE_NOW, AFTER_TMOBILE_ACCOUNT, MANUAL_REQUIRED,
              NEEDS_IDENTITY, NEEDS_CREDENTIALS, UNKNOWN_TYPE, DATA_CONFLICT)

LIVE_VENDORS = frozenset({"vola", "tmobile"})
_DIGITS = re.compile(r"\D")
_PHONE_LIKE = re.compile(r"^\+?\d[\d\-\s().]{8,}$")

# Identity hints: substring in any identity text -> (likely vendor, likely class)
_HINT_RULES = (
    (("lm150",), "vola", "VoLTE cellular phone (FlyingVoice LM150)"),
    (("pr12",), "vola", "SIP cellular phone (FlyingVoice PR12)"),
    (("ms130",), "ms130", "MS130v4 line"),
    (("ata", "cisco"), "cisco_ata", "analog/SIP ATA"),
    (("inseego", "fx3100", "fx3110", "fw3100"), "inseego", "cellular modem / static IP"),
    (("teltonika",), "teltonika", "cellular router"),
)


# ── pure helpers (unit-tested) ───────────────────────────────────────────
def _norm(v) -> str:
    return v.strip() if isinstance(v, str) else ("" if v is None else str(v).strip())


def _digits(v) -> str:
    return _DIGITS.sub("", _norm(v))


def _is_phone_like(v) -> bool:
    s = _norm(v)
    return bool(_PHONE_LIKE.match(s)) and 10 <= len(_digits(s)) <= 15


def has_msisdn(d: dict) -> bool:
    return bool(_norm(d.get("msisdn")))


def has_required_identifier(vendor: str, d: dict) -> bool:
    if vendor == "vola":
        return bool(_norm(d.get("serial_number")) or _norm(d.get("imei")))
    if vendor == "tmobile":
        return bool(_norm(d.get("msisdn")) or _norm(d.get("iccid")) or _norm(d.get("imei")))
    return False


def required_identifier(vendor: str) -> str:
    return {"vola": "serial_number or imei", "tmobile": "msisdn"}.get(vendor, "—")


def _live_now(vendor: str, d: dict, configured: bool, tmobile_account: bool) -> bool:
    if vendor == "vola":
        return configured and has_required_identifier("vola", d)
    if vendor == "tmobile":
        return configured and bool(_norm(d.get("msisdn"))) and tmobile_account
    return False


def detect_data_conflict(d: dict, probe_vendors) -> str | None:
    """Concrete, conservative identity contradictions."""
    if _norm(d.get("vola_org_id")) and "vola" not in probe_vendors:
        return "vola_org_id is set but model/type does not classify as Vola"
    serial = d.get("serial_number")
    if _is_phone_like(serial) and _norm(d.get("msisdn")) and _digits(serial) != _digits(d.get("msisdn")):
        return "serial_number looks like a phone number but differs from msisdn"
    return None


def _has_identity_text(d: dict) -> bool:
    return any(_norm(d.get(k)) for k in ("model", "device_type", "manufacturer", "hardware_model_id"))


def categorize_device(d: dict, probe_vendors, *, adapter_configured: dict,
                      tmobile_account_available: bool) -> dict:
    """Pure: classify one device into exactly one operator category + reason."""
    probes = list(probe_vendors)

    conflict = detect_data_conflict(d, probes)
    if conflict:
        return {"category": DATA_CONFLICT, "reason": conflict}

    if not probes:
        if _has_identity_text(d):
            return {"category": UNKNOWN_TYPE,
                    "reason": "has model/type text but no adapter recognises it"}
        return {"category": NEEDS_IDENTITY,
                "reason": "blank inventory row — no model / vendor / identifier"}

    for v in probes:
        if _live_now(v, d, adapter_configured.get(v, False), tmobile_account_available):
            return {"category": MONITORABLE_NOW, "reason": f"{v} live probe ready"}

    if "tmobile" in probes and has_msisdn(d) and not tmobile_account_available:
        return {"category": AFTER_TMOBILE_ACCOUNT,
                "reason": "T-Mobile SubscriberInquiry needs TMOBILE_ACCOUNT_ID (msisdn present)"}

    live = next((v for v in probes if v in LIVE_VENDORS), None)
    if live is not None:
        if has_required_identifier(live, d) and not adapter_configured.get(live, False):
            return {"category": NEEDS_CREDENTIALS,
                    "reason": f"{live} adapter not configured (missing credentials)"}
        if not has_required_identifier(live, d):
            return {"category": NEEDS_IDENTITY,
                    "reason": f"{live} requires {required_identifier(live)} (not present)"}

    return {"category": MANUAL_REQUIRED,
            "reason": "no automated live probe for this device class yet — record a manual test"}


def infer_identity_hints(d: dict) -> dict:
    """Suggest a likely class/vendor + the fields still needed. Never a final mapping."""
    text = " ".join(_norm(d.get(k)) for k in (
        "device_id", "display_name", "model", "device_type", "manufacturer",
        "hardware_model_id", "serial_number")).lower()
    likely_vendor = None
    likely_class = None
    hints: list[str] = []

    for needles, vendor, klass in _HINT_RULES:
        if any(n in text for n in needles):
            likely_vendor, likely_class = vendor, klass
            break

    phone_like_fields = [k for k in ("device_id", "display_name", "serial_number")
                         if _is_phone_like(d.get(k))]
    if phone_like_fields and not likely_vendor:
        likely_class = likely_class or "cellular endpoint"
        hints.append(f"phone-number-like value in {phone_like_fields} → likely a cellular line")

    missing: list[str] = []
    if likely_vendor == "vola":
        if not (_norm(d.get("serial_number")) or _norm(d.get("imei"))):
            missing += ["serial_number", "imei"]
        if not _norm(d.get("vola_org_id")):
            missing.append("vola_org_id")
        action = "Confirm model + capture serial_number (or imei) and vola_org_id"
    elif likely_vendor in ("tmobile", None) and (phone_like_fields or _norm(d.get("carrier"))):
        for f in ("msisdn", "imei", "iccid"):
            if not _norm(d.get(f)):
                missing.append(f)
        action = "Confirm carrier + capture msisdn (and IMEI/ICCID); set TMOBILE_ACCOUNT_ID for live probe"
        likely_vendor = likely_vendor or "tmobile?"
    elif likely_vendor in ("cisco_ata", "ms130", "inseego", "teltonika"):
        action = "Confirm model; capture line identifier; manual verification until adapter is live"
    else:
        action = "Physically identify device; capture model + vendor + one identifier"

    return {
        "likely_device_class": likely_class or "unknown",
        "likely_vendor_candidate": likely_vendor or "unknown",
        "missing_fields": sorted(set(missing)),
        "recommended_action": action,
        "hints": hints,
    }


def build_template_row(d: dict, hints: dict, category: str) -> dict:
    """One row of the PR #81 mapping template — blanks for the operator to fill."""
    return {
        "device_id": d.get("device_id", ""),
        "site_id": d.get("site_id") or "",
        "site_name": d.get("site_name") or "",
        "current_name": d.get("display_name") or "",
        "suggested_model": d.get("model") or "",
        "suggested_vendor": hints["likely_vendor_candidate"],
        "required_identifier": "",
        "imei": "",
        "iccid": "",
        "msisdn": "",
        "serial_number": "",
        "manual_verification_only": category == MANUAL_REQUIRED,
        "operator_notes": hints["recommended_action"],
    }


def summary_counts(reports: list[dict]) -> dict:
    counts = {c: 0 for c in CATEGORIES}
    missing = {"imei": 0, "iccid": 0, "msisdn": 0, "vendor": 0, "model": 0}
    for r in reports:
        counts[r["category"]] += 1
        cur = r["current"]
        if not _norm(cur.get("imei")):
            missing["imei"] += 1
        if not _norm(cur.get("iccid")):
            missing["iccid"] += 1
        if not _norm(cur.get("msisdn")):
            missing["msisdn"] += 1
        if not r["probe_vendors"]:
            missing["vendor"] += 1
        if not _norm(cur.get("model")):
            missing["model"] += 1
    return {
        "total_devices": len(reports),
        "by_category": counts,
        "monitorable_now": counts[MONITORABLE_NOW],
        "blocked_by_tmobile_account_id": counts[AFTER_TMOBILE_ACCOUNT],
        "manual_verification_required": counts[MANUAL_REQUIRED],
        "unmapped": counts[NEEDS_IDENTITY] + counts[UNKNOWN_TYPE],
        "data_conflicts": counts[DATA_CONFLICT],
        "missing_imei": missing["imei"],
        "missing_iccid": missing["iccid"],
        "missing_msisdn": missing["msisdn"],
        "missing_vendor": missing["vendor"],
        "missing_model": missing["model"],
    }


# Fields that may appear in an export — identity/diagnostic only, never secrets.
_EXPORT_DEVICE_FIELDS = (
    "device_id", "display_name", "site_id", "site_name", "customer_id", "tenant_id",
    "model", "device_type", "manufacturer", "hardware_model_id", "carrier",
    "telemetry_source", "vola_org_id", "msisdn", "imei", "iccid", "serial_number",
    "status", "last_heartbeat", "network_status", "identifier_type",
    "reconciliation_status", "import_batch_id",
)


def export_record(report: dict) -> dict:
    """Whitelisted, secret-free record for export."""
    cur = report["current"]
    return {
        **{k: (str(cur.get(k)) if cur.get(k) is not None else "") for k in _EXPORT_DEVICE_FIELDS},
        "category": report["category"],
        "reason": report["reason"],
        "probe_vendors": ",".join(report["probe_vendors"]),
        "likely_vendor_candidate": report["hints"]["likely_vendor_candidate"],
        "likely_device_class": report["hints"]["likely_device_class"],
        "missing_fields": ",".join(report["hints"]["missing_fields"]),
        "recommended_action": report["hints"]["recommended_action"],
    }


# ── DB load (read-only) ──────────────────────────────────────────────────
async def _load(db, tenant_id: str):
    from sqlalchemy import select
    from app.models.device import Device
    from app.models.site import Site
    from app.models.service_unit import ServiceUnit
    from app.services.device_health.classifier import classify
    from app.services.device_health.adapters import get_status_adapter
    from app.config import settings

    sites = {s.site_id: s for s in (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id))).scalars().all()}
    units = {u.device_id: u for u in (await db.execute(
        select(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalars().all() if u.device_id}
    devices = (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id).order_by(Device.device_id))).scalars().all()

    tmobile_account = bool(settings.TMOBILE_ACCOUNT_ID)
    reports = []
    for dv in devices:
        site = sites.get(dv.site_id)
        unit = units.get(dv.device_id)
        cur = {
            "device_id": dv.device_id, "site_id": dv.site_id,
            "site_name": (site.site_name if site else None),
            "customer_id": (site.customer_id if site else None),
            "tenant_id": dv.tenant_id,
            "display_name": (unit.unit_name if unit else (dv.model or dv.device_id)),
            "model": dv.model, "device_type": dv.device_type, "manufacturer": dv.manufacturer,
            "hardware_model_id": dv.hardware_model_id, "carrier": dv.carrier,
            "telemetry_source": dv.telemetry_source, "vola_org_id": dv.vola_org_id,
            "msisdn": dv.msisdn, "imei": dv.imei, "iccid": dv.iccid,
            "serial_number": dv.serial_number, "status": dv.status,
            "last_heartbeat": dv.last_heartbeat, "network_status": dv.network_status,
            "identifier_type": dv.identifier_type,
            "reconciliation_status": dv.reconciliation_status, "import_batch_id": dv.import_batch_id,
        }
        cls = classify(model=dv.model, device_type=dv.device_type,
                       hardware_model_id=dv.hardware_model_id,
                       manufacturer=dv.manufacturer, carrier=dv.carrier)
        probes = list(cls.probe_vendors)
        adapter_configured = {v: bool(get_status_adapter(v).is_configured) for v in probes}
        cat = categorize_device(cur, probes, adapter_configured=adapter_configured,
                                tmobile_account_available=tmobile_account)
        hints = infer_identity_hints(cur)
        reports.append({
            "current": cur, "probe_vendors": probes,
            "classifier": {"connection_type": cls.connection_type, "voice_type": cls.voice_type,
                           "vendor_cloud": cls.vendor_cloud, "carrier_vendor": cls.carrier_vendor},
            "adapter_candidate": (probes[0] if probes else None),
            "category": cat["category"], "reason": cat["reason"], "hints": hints,
        })
    return reports


def _print(reports: list[dict], summary: dict) -> None:
    print("=" * 72)
    print(f"RH device identity discovery — READ-ONLY  (tenant: {RH_TENANT})")
    print("=" * 72)
    for r in reports:
        c = r["current"]
        print(f"\n  {c['device_id']}  [{r['category']}]")
        print(f"    site={c['site_id']} ({c['site_name']})  cust={c['customer_id']}  status={c['status']}")
        print(f"    model={c['model']!r} type={c['device_type']!r} carrier={c['carrier']!r} "
              f"vendor={c['telemetry_source']!r}")
        print(f"    msisdn={c['msisdn']!r} imei={c['imei']!r} iccid={c['iccid']!r} serial={c['serial_number']!r}")
        print(f"    last_heartbeat={c['last_heartbeat']} network_status={c['network_status']}")
        print(f"    classifier={r['classifier']}  probes={r['probe_vendors']}  adapter={r['adapter_candidate']}")
        print(f"    → {r['reason']}")
        if r["category"] in (NEEDS_IDENTITY, UNKNOWN_TYPE, DATA_CONFLICT, AFTER_TMOBILE_ACCOUNT):
            h = r["hints"]
            print(f"    HINT: likely {h['likely_vendor_candidate']} / {h['likely_device_class']}; "
                  f"missing {h['missing_fields'] or '-'}; action: {h['recommended_action']}")

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"  total devices                 : {summary['total_devices']}")
    for c in CATEGORIES:
        print(f"  {c:30}: {summary['by_category'][c]}")
    for k in ("missing_imei", "missing_iccid", "missing_msisdn", "missing_vendor", "missing_model"):
        print(f"  {k:30}: {summary[k]}")
    print("\n  (Findings only — this script writes nothing.)")


def _write_export(path: str, reports: list[dict]) -> None:
    records = [export_record(r) for r in reports]
    if path.lower().endswith(".csv"):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            if records:
                w = csv.DictWriter(fh, fieldnames=list(records[0].keys()))
                w.writeheader()
                w.writerows(records)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)
    print(f"\nExported {len(records)} record(s) to {path} (identity/diagnostics only — no secrets).")


async def run(export_path: str | None = None) -> dict:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        reports = await _load(db, RH_TENANT)
        await db.rollback()  # belt-and-suspenders: this audit never writes
    summary = summary_counts(reports)
    _print(reports, summary)
    if export_path:
        _write_export(export_path, reports)
    return summary


def main() -> None:
    export_path = None
    argv = sys.argv[1:]
    if "--export" in argv:
        i = argv.index("--export")
        if i + 1 < len(argv):
            export_path = argv[i + 1]
    try:
        asyncio.run(run(export_path=export_path))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: discovery audit aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
