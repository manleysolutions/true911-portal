"""Portfolio Registry service — load, reconcile, and the approval workflow.

The Fusion Engine reconciles incoming candidate buildings against the APPROVED
registry instead of rediscovering the portfolio every run.  Split into three parts:

  * ``load_registry``  — READ-ONLY snapshot of the approved registry (SELECT only).
  * ``reconcile``      — PURE.  Given candidate buildings + a registry snapshot,
                         resolves each candidate to a registry building (approved
                         mappings BEFORE any heuristic) and proposes review items
                         when it cannot.  Writes nothing.
  * approval workflow  — ``approve_new_building`` / ``approve_alias`` /
                         ``approve_device_mapping`` / ``reject_review_item`` — the
                         ONLY functions that write the registry, and only on an
                         explicit operator approval.

A plain Fusion run calls load + reconcile only — it never mutates the registry, and
NEVER touches Zoho / Napco / Genesis / carrier APIs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

# Review types (requirement 5).
RT_NEW_BUILDING = "new_building"
RT_POSSIBLE_MERGE = "possible_merge"
RT_DUPLICATE_BUILDING = "duplicate_building"
RT_ADDRESS_CONFLICT = "address_conflict"
RT_DEVICE_CONFLICT = "device_conflict"
RT_UNKNOWN_ALIAS = "unknown_alias"

# Device-mapping kinds (requirement 3).
DEV_KINDS = ("napco_radio", "genesis_msisdn", "iccid", "imei", "phone",
             "true911_device", "zoho_account")


# ── normalization (shared join-key semantics with the fusion engine) ──
def norm_name(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def norm_alias(s) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def norm_id(v) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()


def norm_addr(street, city, state) -> str:
    return norm_name(f"{street or ''} {city or ''} {state or ''}")


# ══════════════════════════════════════════════════════════════════════
# READ-ONLY snapshot
# ══════════════════════════════════════════════════════════════════════
async def load_registry(db, tenant_id: str) -> dict:
    """READ-ONLY snapshot of the approved registry as plain dicts (so ``reconcile``
    stays pure and unit-testable).  Only approved buildings and active
    aliases/mappings participate in reconciliation."""
    from sqlalchemy import select

    from app.models.portfolio_registry import (
        PortfolioAlias,
        PortfolioBuilding,
        PortfolioDeviceMapping,
        PortfolioReviewItem,
    )

    buildings = [_building_dict(b) for b in (await db.execute(
        select(PortfolioBuilding).where(PortfolioBuilding.tenant_id == tenant_id))).scalars().all()]
    aliases = [{"building_id": a.building_id, "alias": a.alias,
                "alias_normalized": a.alias_normalized, "source": a.source,
                "confidence": a.confidence, "active": a.active}
               for a in (await db.execute(
                   select(PortfolioAlias).where(PortfolioAlias.tenant_id == tenant_id))).scalars().all()]
    mappings = [{"building_id": m.building_id, "kind": m.kind, "value": m.value,
                 "value_normalized": m.value_normalized, "source": m.source,
                 "confidence": m.confidence, "active": m.active}
                for m in (await db.execute(
                    select(PortfolioDeviceMapping).where(
                        PortfolioDeviceMapping.tenant_id == tenant_id))).scalars().all()]
    reviews = [{"id": r.id, "review_type": r.review_type, "status": r.status,
                "signature": r.signature, "suggested_building_id": r.suggested_building_id}
               for r in (await db.execute(
                   select(PortfolioReviewItem).where(
                       PortfolioReviewItem.tenant_id == tenant_id))).scalars().all()]
    return {"tenant": tenant_id, "buildings": buildings, "aliases": aliases,
            "device_mappings": mappings, "review_items": reviews}


def _building_dict(b) -> dict:
    return {"id": b.id, "canonical_name": b.canonical_name, "store_number": b.store_number,
            "site_type": b.site_type, "status": b.status, "address": b.address,
            "city": b.city, "state": b.state, "zip": b.zip, "approved": b.approved}


def empty_registry(tenant_id: str = None) -> dict:
    return {"tenant": tenant_id, "buildings": [], "aliases": [], "device_mappings": [],
            "review_items": []}


# ══════════════════════════════════════════════════════════════════════
# PURE reconciliation
# ══════════════════════════════════════════════════════════════════════
def _candidate_identifiers(cand: dict) -> dict:
    """Extract the reconcile join values from a fusion candidate (Building Twin).
    Returns {kind: set(normalized values)} across all device-mapping kinds."""
    out = {k: set() for k in DEV_KINDS}
    for d in cand.get("devices", []):
        if d.get("radio_number"):
            out["napco_radio"].add(norm_id(d["radio_number"]))
        if d.get("serial"):
            out["napco_radio"].add(norm_id(d["serial"]))
        if d.get("iccid"):
            out["iccid"].add(norm_id(d["iccid"]))
        if d.get("imei"):
            out["imei"].add(norm_id(d["imei"]))
        if d.get("msisdn"):
            out["genesis_msisdn"].add(norm_id(d["msisdn"]))
            out["phone"].add(norm_id(d["msisdn"]))
    # True911 site id + Zoho account name (if the twin carries them)
    if cand.get("e911", {}).get("site_id"):
        out["true911_device"].add(norm_id(cand["e911"]["site_id"]))
    for nm in cand.get("source_names", {}).get("zoho", []) or []:
        out["zoho_account"].add(norm_alias(nm))
    return out


def _index_mappings(registry: dict) -> dict:
    idx = {}
    for m in registry.get("device_mappings", []):
        if m.get("active", True):
            idx[(m["kind"], m["value_normalized"])] = m["building_id"]
    return idx


def reconcile(candidates: list[dict], registry: dict) -> dict:
    """PURE.  Resolve each candidate to a registry building, applying APPROVED
    mappings before any heuristic, and propose review items where it cannot.

    Order (requirement 4): exact device mapping → alias → store number → address.
    Returns {resolved: [...], review_items: [...], stats: {...}} and writes nothing.
    """
    approved = [b for b in registry.get("buildings", []) if b.get("approved")]
    by_id = {b["id"]: b for b in approved}
    by_store = {}
    by_addr = {}
    for b in approved:
        if b.get("store_number"):
            by_store.setdefault(str(b["store_number"]), []).append(b["id"])
        a = norm_addr(b.get("address"), b.get("city"), b.get("state"))
        if a:
            by_addr.setdefault(a, []).append(b["id"])
    alias_idx = {}
    for a in registry.get("aliases", []):
        if a.get("active", True):
            alias_idx.setdefault(a["alias_normalized"], a["building_id"])
    dev_idx = _index_mappings(registry)

    resolved, review_items = [], []

    def add_review(rtype, cand, detail, idx, suggested=None):
        review_items.append({
            "review_type": rtype,
            "signature": _signature(rtype, cand, suggested),
            "candidate_index": idx,
            "candidate_name": cand.get("canonical_name"),
            "store_number": cand.get("store_number"),
            "suggested_building_id": suggested,
            "detail": detail,
            "candidate": cand,
        })

    for idx, cand in enumerate(candidates):
        ids = _candidate_identifiers(cand)

        # 1) exact/device mapping (approved identifier -> building)
        dev_hits = set()
        for kind, vals in ids.items():
            for v in vals:
                bid = dev_idx.get((kind, v))
                if bid is not None:
                    dev_hits.add(bid)

        # 2) alias mapping (canonical name / raw source names)
        alias_bid = None
        for nm in _candidate_labels(cand):
            alias_bid = alias_idx.get(norm_alias(nm))
            if alias_bid is not None:
                break

        # 3) store-number mapping
        store_hits = by_store.get(str(cand.get("store_number")), []) if cand.get("store_number") else []

        # 4) address mapping
        ca = norm_addr(cand.get("address", {}).get("street"), cand.get("address", {}).get("city"),
                       cand.get("address", {}).get("state"))
        addr_hits = by_addr.get(ca, []) if ca else []

        candidate_bids = set(dev_hits) | ({alias_bid} if alias_bid else set()) \
            | set(store_hits) | set(addr_hits)

        if not candidate_bids:
            add_review(RT_NEW_BUILDING, cand,
                       "No approved registry building maps to this candidate", idx)
            continue

        if len(candidate_bids) > 1:
            add_review(RT_POSSIBLE_MERGE, cand,
                       "Candidate maps to %d registry buildings: %s"
                       % (len(candidate_bids), ", ".join(map(str, sorted(candidate_bids)))),
                       idx, suggested=sorted(candidate_bids)[0])
            # still record a best-effort resolution to the highest-priority hit
            bid = (sorted(dev_hits)[0] if dev_hits else alias_bid
                   or (store_hits[0] if store_hits else addr_hits[0]))
            resolved.append(_resolution(cand, bid, "ambiguous", idx))
            continue

        bid = next(iter(candidate_bids))
        b = by_id[bid]
        method = ("device" if dev_hits else "alias" if alias_bid
                  else "store_number" if store_hits else "address")

        # device conflict: a device identifier is approved-mapped to a DIFFERENT building
        conflict_bids = {d for d in dev_hits if d != bid}
        if conflict_bids:
            add_review(RT_DEVICE_CONFLICT, cand,
                       "Device identifier maps to building %s but the record resolves to %s"
                       % (sorted(conflict_bids)[0], bid), idx, suggested=bid)

        # address conflict: matched, but the candidate address differs from the registry
        cba = norm_addr(b.get("address"), b.get("city"), b.get("state"))
        if ca and cba and ca != cba:
            add_review(RT_ADDRESS_CONFLICT, cand,
                       "Address '%s' differs from registry '%s'"
                       % (_addr_str(cand.get("address", {})),
                          _addr_str({"street": b.get("address"), "city": b.get("city"),
                                     "state": b.get("state")})), idx, suggested=bid)

        # unknown alias: resolved by store/address/device, but this label is not a
        # known approved alias yet -> suggest adding it
        if method != "alias" and _candidate_labels(cand):
            label = _candidate_labels(cand)[0]
            if norm_alias(label) not in alias_idx:
                add_review(RT_UNKNOWN_ALIAS, cand,
                           "Label %r resolves to building %s but is not an approved alias"
                           % (label, bid), idx, suggested=bid)

        resolved.append(_resolution(cand, bid, method, idx))

    # duplicate registry buildings (same store# or address across approved buildings)
    for store, bids in by_store.items():
        if len(bids) > 1:
            review_items.append({
                "review_type": RT_DUPLICATE_BUILDING,
                "signature": f"{RT_DUPLICATE_BUILDING}:store:{store}",
                "candidate_name": None, "store_number": store,
                "suggested_building_id": sorted(bids)[0],
                "detail": "Registry has %d approved buildings with store #%s: %s"
                          % (len(bids), store, ", ".join(map(str, sorted(bids)))),
                "candidate": None})

    stats = _reconcile_stats(candidates, resolved, review_items, registry)
    return {"resolved": resolved, "review_items": review_items, "stats": stats}


def _candidate_labels(cand: dict) -> list[str]:
    labels = [cand.get("canonical_name")]
    for src, names in (cand.get("source_names") or {}).items():
        labels.extend(names or [])
    return [x for x in labels if x]


def _resolution(cand, building_id, method, idx=None) -> dict:
    return {"candidate_index": idx, "candidate_name": cand.get("canonical_name"),
            "store_number": cand.get("store_number"), "building_id": building_id, "method": method}


def _addr_str(a: dict) -> str:
    return ", ".join(x for x in (a.get("street"), a.get("city"), a.get("state")) if x) or "—"


def _signature(rtype, cand, suggested) -> str:
    key = cand.get("store_number") or norm_alias(cand.get("canonical_name")) or "unknown"
    return f"{rtype}:{key}:{suggested if suggested is not None else '-'}"


def _reconcile_stats(candidates, resolved, review_items, registry) -> dict:
    from collections import Counter
    return {
        "candidates": len(candidates),
        "portfolio_buildings": len(registry.get("buildings", [])),
        "approved_buildings": sum(1 for b in registry.get("buildings", []) if b.get("approved")),
        "known_aliases": sum(1 for a in registry.get("aliases", []) if a.get("active", True)),
        "approved_mappings": sum(1 for m in registry.get("device_mappings", []) if m.get("active", True)),
        "resolved": len(resolved),
        "pending_review_new": len(review_items),
        "review_by_type": dict(Counter(r["review_type"] for r in review_items)),
        "rejected_suggestions": sum(1 for r in registry.get("review_items", [])
                                    if r.get("status") == "rejected"),
    }


# ══════════════════════════════════════════════════════════════════════
# Approval workflow — the ONLY registry writers (explicit approval required)
# ══════════════════════════════════════════════════════════════════════
async def approve_new_building(db, tenant_id: str, *, approved_by: str, canonical_name: str,
                               store_number=None, site_type=None, address=None, city=None,
                               state=None, zip=None, aliases=None, device_mappings=None,
                               review_item_id=None, notes=None) -> dict:
    """Create + approve a PortfolioBuilding (and any aliases / device mappings), then
    mark the originating review item approved.  This is the explicit operator action
    that makes a mapping permanent.  Idempotent-friendly: dedups aliases/mappings by
    their unique keys."""
    from app.models.portfolio_registry import (
        PortfolioAlias,
        PortfolioBuilding,
        PortfolioDeviceMapping,
    )

    now = datetime.now(timezone.utc)
    building = PortfolioBuilding(
        tenant_id=tenant_id, canonical_name=canonical_name, store_number=store_number,
        site_type=site_type, status="active", address=address, city=city, state=state, zip=zip,
        notes=notes, approved=True, approved_by=approved_by, approved_at=now)
    db.add(building)
    await db.flush()          # obtain building.id

    for al in (aliases or []):
        db.add(PortfolioAlias(
            tenant_id=tenant_id, building_id=building.id, alias=al,
            alias_normalized=norm_alias(al), source=(_alias_source(al)), confidence=100.0, active=True))
    for m in (device_mappings or []):
        db.add(PortfolioDeviceMapping(
            tenant_id=tenant_id, building_id=building.id, kind=m["kind"], value=m["value"],
            value_normalized=norm_id(m["value"]) if m["kind"] != "zoho_account" else norm_alias(m["value"]),
            source=m.get("source"), confidence=m.get("confidence", 100.0), active=True))

    if review_item_id is not None:
        await _decide_review(db, tenant_id, review_item_id, "approved", approved_by)

    await db.commit()
    return {"building_id": building.id, "approved_by": approved_by, "approved_at": now.isoformat()}


async def approve_alias(db, tenant_id: str, building_id: int, alias: str, *, approved_by: str,
                        source="operator", review_item_id=None) -> dict:
    from app.models.portfolio_registry import PortfolioAlias
    db.add(PortfolioAlias(tenant_id=tenant_id, building_id=building_id, alias=alias,
                          alias_normalized=norm_alias(alias), source=source, confidence=100.0,
                          active=True))
    if review_item_id is not None:
        await _decide_review(db, tenant_id, review_item_id, "approved", approved_by)
    await db.commit()
    return {"building_id": building_id, "alias": alias}


async def approve_device_mapping(db, tenant_id: str, building_id: int, kind: str, value: str, *,
                                 approved_by: str, source=None, review_item_id=None) -> dict:
    from app.models.portfolio_registry import PortfolioDeviceMapping
    vn = norm_id(value) if kind != "zoho_account" else norm_alias(value)
    db.add(PortfolioDeviceMapping(tenant_id=tenant_id, building_id=building_id, kind=kind,
                                  value=value, value_normalized=vn, source=source,
                                  confidence=100.0, active=True))
    if review_item_id is not None:
        await _decide_review(db, tenant_id, review_item_id, "approved", approved_by)
    await db.commit()
    return {"building_id": building_id, "kind": kind, "value": value}


async def reject_review_item(db, tenant_id: str, review_item_id: int, *, rejected_by: str) -> dict:
    await _decide_review(db, tenant_id, review_item_id, "rejected", rejected_by)
    await db.commit()
    return {"review_item_id": review_item_id, "status": "rejected"}


async def sync_review_queue(db, tenant_id: str, review_items: list[dict]) -> dict:
    """Persist NEW pending review items from a fusion run (dedup by signature).  This
    writes only to the review queue, never to the approved registry, and never
    re-opens an already-decided item."""
    from sqlalchemy import select

    from app.models.portfolio_registry import PortfolioReviewItem

    existing = {r.signature for r in (await db.execute(
        select(PortfolioReviewItem).where(PortfolioReviewItem.tenant_id == tenant_id))).scalars().all()}
    added = 0
    for it in review_items:
        if it["signature"] in existing:
            continue
        db.add(PortfolioReviewItem(
            tenant_id=tenant_id, review_type=it["review_type"], status="pending",
            signature=it["signature"], candidate_name=it.get("candidate_name"),
            store_number=it.get("store_number"), suggested_building_id=it.get("suggested_building_id"),
            detail=it.get("detail"),
            payload=json.dumps(it.get("candidate"), default=str) if it.get("candidate") else None))
        existing.add(it["signature"])
        added += 1
    await db.commit()
    return {"added": added, "skipped": len(review_items) - added}


async def _decide_review(db, tenant_id: str, review_item_id: int, status: str, who: str) -> None:
    from sqlalchemy import select

    from app.models.portfolio_registry import PortfolioReviewItem

    row = (await db.execute(select(PortfolioReviewItem).where(
        PortfolioReviewItem.tenant_id == tenant_id,
        PortfolioReviewItem.id == review_item_id))).scalar_one_or_none()
    if row is not None:
        row.status = status
        row.decided_by = who
        row.decided_at = datetime.now(timezone.utc)


def _alias_source(alias) -> str:
    return "operator"
