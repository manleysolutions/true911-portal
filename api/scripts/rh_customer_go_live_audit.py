"""RH customer go-live audit — the definitive "can we send Judy's invite?" report.

READ-ONLY.  Runs every check that decides whether the RH customer experience is
ready, and SEPARATES the two kinds of outstanding work, because they have
different owners and different consequences:

  * SYSTEM BLOCKERS   — Manley / platform work that must be done BEFORE the
                        invite (flags off, dashboard not in registry mode,
                        unresolved identity, a store number on the wrong
                        location, duplicate buildings, a Devices KPI of 0 …).
  * CUSTOMER ACTIONS  — legitimate work Judy does AFTER she logs in (confirm
                        E911 for each location, add site contacts, answer a
                        request).  These never block: the console exists so she
                        can do them herself.

Warnings (system follow-ups that are honest in the UI and do not block) are
listed separately.

Verdict:  READY · READY_WITH_CUSTOMER_ACTIONS · BLOCKED
Exit:     0 READY · 1 READY_WITH_CUSTOMER_ACTIONS · 2 BLOCKED · 3 error

Only SELECTs — never writes Zoho / Napco / Genesis / carrier / True911 / registry,
never marks E911 verified, never sends an invite.

Usage (Render shell, api service):
    python -m scripts.rh_customer_go_live_audit --tenant restoration-hardware
    python -m scripts.rh_customer_go_live_audit --tenant restoration-hardware --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_TENANT = os.environ.get("RH_READINESS_TENANT", "restoration-hardware")

READY = "READY"
READY_WITH_CUSTOMER_ACTIONS = "READY_WITH_CUSTOMER_ACTIONS"
BLOCKED = "BLOCKED"

# Operator-confirmed store numbers (keyword must appear in the canonical name or
# city of the ONE building carrying that store number).
CONFIRMED_STORES = [
    ("Chicago", "147"), ("Austin", "149"), ("Dallas", "168"), ("Charlotte", "174"),
    ("Oak Brook", "176"), ("Cherry Hill", "640"), ("Katy", "645"), ("Irvine", "646"),
    ("Boca Raton", "654"), ("Pembroke", "661"), ("Roseville", "123"), ("Edina", "159"),
    ("Dawsonville", "604"), ("Gilbert", "642"), ("San Rafael", "656"),
]
# Operator-confirmed named / special locations — each must be exactly ONE building.
# (label, name/city keywords, address keywords)
CONFIRMED_NAMED = [
    ("Princeton (3265 Brunswick Pike)", ("princeton",), ("brunswick",)),
    ("Pleasanton Gallery", ("pleasanton",), ()),
    ("Hollywood Gallery", ("hollywood",), ()),
    ("LaSalle Gallery", ("lasalle", "la salle"), ()),
    ("RH NYC Flagship", ("rhnyc", "rh nyc", "nyc flagship", "new york flagship"), ()),
    ("Patterson Warehouse", ("patterson",), ()),
    ("MDC", ("mdc",), ()),
    ("Beverly Modern Gallery", ("beverly modern",), ()),
    ("Linden House Gallery", ("linden",), ()),
    ("Soda Grocery Gallery", ("soda grocery", "soda"), ()),
    ("Greenwich Gallery", ("greenwich",), ()),
    ("Richmond Gallery", ("richmond",), ()),
]
# Memphis stays its own retail/gallery location pending better evidence: more
# than one Memphis building is surfaced for review, never auto-merged.
MEMPHIS = ("memphis",)
KEEP_SEPARATE = (("Edina", "159"), ("Raleigh", "178"))
IDENTITY_REVIEW_TYPES = {"possible_merge", "duplicate_building", "device_conflict",
                         "address_conflict"}


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _has(hay, keywords) -> bool:
    h = f" {_norm(hay)} "
    return any(f" {_norm(k)} " in h or _norm(k).replace(" ", "") in h.replace(" ", "")
               for k in keywords)


def _valid_store(s) -> bool:
    s = str(s or "").strip()
    return s.isdigit() and int(s) > 0


# ══════════════════════════════════════════════════════════════════════
# PURE evaluation (no DB) — facts in, verdict out
# ══════════════════════════════════════════════════════════════════════
def check_known_locations(buildings: list[dict]) -> tuple[list, list, list]:
    """(blockers, warnings, results) for the operator-confirmed mappings."""
    blockers, warnings, results = [], [], []

    def hay(b):
        return f"{b.get('canonical_name') or ''} {b.get('city') or ''}"

    for kw, store in CONFIRMED_STORES:
        with_store = [b for b in buildings if str(b.get("store_number") or "").lstrip("0") == store]
        named = [b for b in buildings if _has(hay(b), (kw,))]
        if len(with_store) > 1:
            blockers.append(f"Store #{store} is on {len(with_store)} buildings (duplicate identity).")
            results.append((f"{kw} #{store}", "DUPLICATE"))
        elif len(with_store) == 1 and not _has(hay(with_store[0]), (kw,)):
            blockers.append(f"Store #{store} is recorded on '{with_store[0]['canonical_name']}', "
                            f"expected {kw}.")
            results.append((f"{kw} #{store}", "WRONG_LOCATION"))
        elif len(with_store) == 1:
            results.append((f"{kw} #{store}", "OK"))
        elif named and any(_valid_store(b.get("store_number")) for b in named):
            wrong = next(b for b in named if _valid_store(b.get("store_number")))
            blockers.append(f"{kw} is recorded as #{wrong['store_number']}, expected #{store}.")
            results.append((f"{kw} #{store}", "WRONG_STORE_NUMBER"))
        elif named:
            warnings.append(f"{kw} is in the portfolio but its store number (#{store}) is not recorded.")
            results.append((f"{kw} #{store}", "STORE_NUMBER_MISSING"))
        else:
            warnings.append(f"{kw} #{store} was not found in the approved portfolio.")
            results.append((f"{kw} #{store}", "NOT_FOUND"))

    for label, name_kw, addr_kw in CONFIRMED_NAMED:
        hits = [b for b in buildings
                if _has(hay(b), name_kw) or (addr_kw and _has(b.get("address"), addr_kw))]
        if len(hits) == 1:
            results.append((label, "OK"))
        elif not hits:
            warnings.append(f"{label} was not found in the approved portfolio.")
            results.append((label, "NOT_FOUND"))
        else:
            blockers.append(f"{label} appears as {len(hits)} buildings — merge not applied.")
            results.append((label, "DUPLICATE"))

    memphis = [b for b in buildings if _has(hay(b), MEMPHIS)]
    if len(memphis) == 1:
        results.append(("Memphis (separate retail/gallery)", "OK"))
    elif not memphis:
        warnings.append("Memphis was not found in the approved portfolio.")
        results.append(("Memphis (separate retail/gallery)", "NOT_FOUND"))
    else:
        warnings.append(f"Memphis appears as {len(memphis)} buildings — review with better "
                        "evidence; do not merge silently.")
        results.append(("Memphis (separate retail/gallery)", "REVIEW"))

    sep = {}
    for kw, store in KEEP_SEPARATE:
        sep[kw] = [b for b in buildings if str(b.get("store_number") or "") == store
                   or _has(hay(b), (kw,))]
    shared = {b["id"] for b in sep["Edina"]} & {b["id"] for b in sep["Raleigh"]}
    if shared:
        blockers.append("Edina #159 and Raleigh #178 are merged into one building — they must stay separate.")
        results.append(("Edina #159 / Raleigh #178 separate", "MERGED"))
    else:
        results.append(("Edina #159 / Raleigh #178 separate", "OK"))
    return blockers, warnings, results


def evaluate(f: dict) -> dict:
    """Classify the gathered facts into SYSTEM BLOCKERS / WARNINGS / CUSTOMER
    ACTIONS and a verdict.  Pure — unit-tested without a database."""
    blockers, warnings, actions = [], [], []
    fl = f["flags"]
    if not fl["customer_api_enabled"]:
        blockers.append("Customer API is not enabled for the tenant (FEATURE_CUSTOMER_API + "
                        "CUSTOMER_API_TENANT_ALLOWLIST).")
    if fl["dashboard_mode"] != "registry_mode":
        blockers.append(f"Customer dashboard is in {fl['dashboard_mode']} — it must render the "
                        "approved Portfolio Registry (FEATURE_CUSTOMER_PORTFOLIO_REGISTRY + allowlist, "
                        "approved buildings).")
    if not fl["self_service_enabled"]:
        blockers.append("Customer self-service is not enabled for the tenant "
                        "(FEATURE_CUSTOMER_SELF_SERVICE + CUSTOMER_SELF_SERVICE_TENANT_ALLOWLIST).")
    elif fl["self_service_user_allowlist"]:
        warnings.append("Self-service is limited to the user allowlist "
                        f"({', '.join(fl['self_service_user_allowlist'])}) — clear "
                        "CUSTOMER_SELF_SERVICE_USER_ALLOWLIST before Judy logs in.")
    if f["customer_visible_buildings"] == 0:
        blockers.append("No customer-visible buildings.")

    rv = f["pending_reviews_by_type"]
    identity = {k: v for k, v in rv.items() if k in IDENTITY_REVIEW_TYPES}
    if identity:
        blockers.append("Unresolved location identity in the registry review queue: "
                        + ", ".join(f"{k}={v}" for k, v in sorted(identity.items())) + ".")
    other = {k: v for k, v in rv.items() if k not in IDENTITY_REVIEW_TYPES}
    if other:
        warnings.append("Registry review items pending (not customer-visible): "
                        + ", ".join(f"{k}={v}" for k, v in sorted(other.items())) + ".")
    if f["pending_building_rows"]:
        warnings.append(f"{f['pending_building_rows']} unapproved building row(s) hidden from the customer.")

    for store, n in f["duplicate_store_numbers"].items():
        blockers.append(f"Store #{store} is on {n} approved buildings.")
    for addr, n in f["duplicate_addresses"].items():
        warnings.append(f"{n} approved buildings share the address '{addr}' — confirm they are distinct.")
    for name, store in f["invalid_store_numbers"]:
        warnings.append(f"'{name}' has placeholder store number '{store}' (hidden from the customer) "
                        "— correct it in the registry.")

    if f["physical_devices"] == 0 and f["device_anchor_mappings"] > 0:
        blockers.append("Devices KPI is 0 although approved device mappings exist.")
    if f["unlinked_buildings"]:
        warnings.append(f"{len(f['unlinked_buildings'])} building(s) have no linked True911 monitoring "
                        "record and show as Unknown: " + ", ".join(f["unlinked_buildings"][:12])
                        + ("…" if len(f["unlinked_buildings"]) > 12 else ""))
    if f["e911_no_address"]:
        warnings.append(f"{f['e911_no_address']} location(s) have no dispatch address on file.")

    kb, kw, _results = check_known_locations(f["buildings"])
    blockers.extend(kb)
    warnings.extend(kw)

    if f["e911_customer_confirmation"]:
        actions.append(f"Confirm E911 for {f['e911_customer_confirmation']} location(s) "
                       "(Verify E911 in each location).")
    if f["locations_missing_contacts"]:
        actions.append(f"Add a facility or emergency contact for {f['locations_missing_contacts']} "
                       "location(s).")
    if f["requests_waiting_customer"]:
        actions.append(f"Respond to {f['requests_waiting_customer']} request(s) waiting on the customer.")

    verdict = BLOCKED if blockers else (READY_WITH_CUSTOMER_ACTIONS if actions else READY)
    return {"verdict": verdict, "system_blockers": blockers, "warnings": warnings,
            "customer_actions": actions, "known_locations": _results}


# ══════════════════════════════════════════════════════════════════════
# Fact gathering (READ-ONLY)
# ══════════════════════════════════════════════════════════════════════
async def gather(db, tenant: str, now=None) -> dict:
    from sqlalchemy import select

    from app.config import settings
    from app.models.portfolio_registry import (
        PortfolioBuilding,
        PortfolioDeviceMapping,
        PortfolioReviewItem,
    )
    from app.models.site import Site
    from app.services.customer import physical_devices as pdev
    from app.services.customer import portfolio_registry_view as prv
    from app.services.customer import self_service as ss

    now = now or datetime.now(timezone.utc)
    buildings = (await db.execute(select(PortfolioBuilding).where(
        PortfolioBuilding.tenant_id == tenant))).scalars().all()
    approved = [b for b in buildings if b.approved]
    reviews = (await db.execute(select(PortfolioReviewItem).where(
        PortfolioReviewItem.tenant_id == tenant,
        PortfolioReviewItem.status == "pending"))).scalars().all()
    mappings = (await db.execute(select(PortfolioDeviceMapping).where(
        PortfolioDeviceMapping.tenant_id == tenant,
        PortfolioDeviceMapping.active.is_(True)))).scalars().all()
    legacy_sites = (await db.execute(select(Site.site_id).where(Site.tenant_id == tenant))).all()

    customer_api = (settings.FEATURE_CUSTOMER_API == "true"
                    and tenant in settings.customer_api_tenant_id_set)
    registry_on = prv.registry_mode_enabled(tenant)
    ss_tenant = (settings.FEATURE_CUSTOMER_SELF_SERVICE == "true"
                 and tenant in settings.customer_self_service_tenant_id_set)
    records = await prv.load_customer_buildings(db, tenant, now) if registry_on else None
    mode = ("legacy_site_mode" if not registry_on
            else "registry_mode" if records is not None else "fallback_mode")

    visible = records or []
    requests = await ss.load_requests(db, tenant)
    req_by_loc: dict = {}
    for r in requests:
        req_by_loc.setdefault(r.location_key, []).append(r)
    overlay = ss.overlay_by_subject(await ss._field_rows(db, tenant))

    e911_states = Counter()
    e911_confirm = e911_no_addr = missing_contacts = 0
    unlinked = []
    for r in visible:
        key = f"bldg:{r['id']}"
        st = ss.e911_state(official_verified=bool(r.get("e911_verified")),
                           has_address=bool(r.get("address")),
                           latest_request=ss._latest_e911_request(req_by_loc.get(key, [])))
        e911_states[st["state"]] += 1
        if st["customer_action_required"]:
            e911_confirm += 1
        if st["state"] == "not_verified":
            e911_no_addr += 1
        loc_ov = overlay.get(key, {}).get("", {})
        if not any(loc_ov.get(f"contact.{c}") for c in ss.CONTACT_ROLES):
            missing_contacts += 1
        if not r.get("_site_ids"):
            unlinked.append(r.get("canonical_name") or f"building {r['id']}")

    store_counts = Counter(str(b.store_number).lstrip("0") for b in approved
                           if _valid_store(b.store_number))
    addr_counts = Counter(_norm(f"{b.address} {b.city} {b.state}") for b in approved if b.address)
    open_reqs = [r for r in requests if r.status not in ss.TERMINAL_STATUSES]
    return {
        "tenant": tenant,
        "as_of": now.isoformat(),
        "flags": {
            "customer_api_enabled": customer_api,
            "customer_preview_enabled": (settings.FEATURE_CUSTOMER_PREVIEW == "true"
                                         and tenant in settings.customer_preview_tenant_id_set),
            "registry_mode_enabled": registry_on,
            "self_service_enabled": ss_tenant,
            "self_service_user_allowlist": sorted(settings.customer_self_service_user_set),
            "dashboard_mode": mode,
        },
        "canonical_buildings": len(approved),
        "pending_building_rows": len(buildings) - len(approved),
        "legacy_sites": len(legacy_sites),
        "customer_visible_buildings": len(visible),
        "protected_buildings": sum(1 for r in visible
                                   if (r.get("protection") or {}).get("status") == "Protected"),
        "physical_devices": sum(r.get("physical_device_count", 0) for r in visible),
        "device_anchor_mappings": sum(1 for m in mappings if m.kind in pdev.ANCHOR_MAPPING_KINDS),
        "telephone_numbers": sum(r.get("phone_count", 0) for r in visible),
        "e911_verified": e911_states.get("verified", 0),
        "e911_states": dict(e911_states),
        "e911_customer_confirmation": e911_confirm,
        "e911_no_address": e911_no_addr,
        "pending_reviews": len(reviews),
        "pending_reviews_by_type": dict(Counter(r.review_type for r in reviews)),
        "open_customer_requests": len(open_reqs),
        "requests_waiting_customer": sum(1 for r in open_reqs if r.status == "waiting_customer"),
        "locations_missing_contacts": missing_contacts,
        "unlinked_buildings": unlinked,
        "duplicate_store_numbers": {s: n for s, n in store_counts.items() if n > 1},
        "duplicate_addresses": {a: n for a, n in addr_counts.items() if n > 1},
        "invalid_store_numbers": [(b.canonical_name, b.store_number) for b in approved
                                  if b.store_number not in (None, "")
                                  and not _valid_store(b.store_number)],
        "buildings": [{"id": b.id, "canonical_name": b.canonical_name,
                       "store_number": b.store_number, "city": b.city, "address": b.address}
                      for b in approved],
    }


async def run_audit(tenant: str) -> dict:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        facts = await gather(db, tenant)
    return {"facts": facts, "report": evaluate(facts)}


# ══════════════════════════════════════════════════════════════════════
# Output
# ══════════════════════════════════════════════════════════════════════
def render(out: dict) -> str:
    f, rep = out["facts"], out["report"]
    fl = f["flags"]
    L = ["=" * 72, f"RH CUSTOMER GO-LIVE AUDIT — {f['tenant']}  ({f['as_of']})", "=" * 72]
    rows = [
        ("Canonical buildings (approved)", f["canonical_buildings"]),
        ("Customer-visible buildings", f["customer_visible_buildings"]),
        ("Protected buildings", f"{f['protected_buildings']}/{f['customer_visible_buildings']}"),
        ("Physical devices", f["physical_devices"]),
        ("Telephone numbers / connections", f["telephone_numbers"]),
        ("E911 verified", f["e911_verified"]),
        ("E911 requiring customer confirmation", f["e911_customer_confirmation"]),
        ("E911 states", ", ".join(f"{k}={v}" for k, v in sorted(f["e911_states"].items())) or "—"),
        ("Pending registry reviews", f["pending_reviews"]),
        ("Open customer service requests", f["open_customer_requests"]),
        ("Locations with missing contacts", f["locations_missing_contacts"]),
        ("Locations with unresolved identity",
         sum(v for k, v in f["pending_reviews_by_type"].items() if k in IDENTITY_REVIEW_TYPES)),
        ("Buildings without linked monitoring", len(f["unlinked_buildings"])),
        ("Legacy Site rows", f["legacy_sites"]),
    ]
    for k, v in rows:
        L.append(f"  {k:<40} {v}")
    L.append("-" * 72)
    L.append("  Feature flags")
    L.append(f"    customer API enabled            {fl['customer_api_enabled']}")
    L.append(f"    customer preview (op. axis)     {fl['customer_preview_enabled']}")
    L.append(f"    registry mode enabled           {fl['registry_mode_enabled']}")
    L.append(f"    customer self-service enabled   {fl['self_service_enabled']}")
    L.append(f"    self-service user allowlist     {', '.join(fl['self_service_user_allowlist']) or '(all users)'}")
    L.append(f"    dashboard mode                  {fl['dashboard_mode']}")
    L.append("-" * 72)
    L.append("  Known locations")
    for label, status in rep["known_locations"]:
        L.append(f"    {'✓' if status == 'OK' else '✗'} {label:<44} {status}")
    for title, items in (("SYSTEM BLOCKERS (fix before the invite)", rep["system_blockers"]),
                         ("WARNINGS (system follow-ups; do not block)", rep["warnings"]),
                         ("CUSTOMER ACTIONS (Judy, after login)", rep["customer_actions"])):
        L.append("-" * 72)
        L.append(f"  {title}: {len(items)}")
        for it in items:
            L.append(f"    • {it}")
    L.append("=" * 72)
    L.append(f"  VERDICT: {rep['verdict']}")
    L.append("  (Read-only — wrote nothing, verified nothing, invited no one.)")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="RH customer go-live audit (read-only).")
    ap.add_argument("--tenant", default=DEFAULT_TENANT)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()
    try:
        out = asyncio.run(run_audit(args.tenant))
    except Exception as exc:
        print(f"ERROR: audit failed — {type(exc).__name__}: {exc}")
        raise SystemExit(3)
    print(json.dumps(out, indent=2, default=str) if args.json else render(out))
    raise SystemExit({READY: 0, READY_WITH_CUSTOMER_ACTIONS: 1, BLOCKED: 2}[out["report"]["verdict"]])


if __name__ == "__main__":
    main()
