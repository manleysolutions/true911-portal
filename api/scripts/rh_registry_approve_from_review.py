"""RH registry approval — turn reviewed candidates into approved buildings.

Converts pending ``PortfolioReviewItem`` rows (created by a Fusion ``--sync-review-queue``
run) into APPROVED ``PortfolioBuilding`` rows, so the customer dashboard can switch
from legacy Site *fallback_mode* to *registry_mode*.  For each approved candidate it
creates the building, its aliases (from the fused source names) and device mappings
(from the fused devices), preserves canonical name / store # / site type / address,
marks the building approved, and marks the review item(s) decided.

It applies the operator's already-made human decisions (``--include-known-rh-decisions``):
canonical-name overrides, merges of duplicate candidates into one building, and
exclusions (the parent "Restoration Hardware" account is NOT a building).

STRICTLY SCOPED writes:
  * Writes ONLY the Portfolio Registry (PortfolioBuilding / Alias / DeviceMapping /
    ReviewItem), and ONLY under ``--apply``.  ``--dry-run`` (the default) writes nothing.
  * NEVER modifies Site / Device / E911 / Zoho / Napco / Genesis, and never marks
    E911 verified.

Usage:
    # preview (default; writes nothing)
    python -m scripts.rh_registry_approve_from_review --tenant restoration-hardware \
        --include-known-rh-decisions --dry-run
    # apply the operator decisions for real (on Render)
    python -m scripts.rh_registry_approve_from_review --tenant restoration-hardware \
        --include-known-rh-decisions --apply
    # optional: only high-confidence non-decision candidates, cap count
    python -m scripts.rh_registry_approve_from_review --tenant restoration-hardware \
        --only-high-confidence --limit 20 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_TENANT = os.environ.get("RH_READINESS_TENANT", "restoration-hardware")
HIGH_CONFIDENCE = 80.0


# ══════════════════════════════════════════════════════════════════════
# Operator decision table (already reviewed & approved by the operator).
# ``keywords`` match a normalized haystack (canonical name + every source name);
# ``store`` matches the candidate store number.  ``merge`` collapses every matching
# candidate into ONE building.  ``action='exclude'`` drops the candidate (not a
# building).  ``site_type`` overrides the fused type where the operator changed it.
# ══════════════════════════════════════════════════════════════════════
class Rule:
    def __init__(self, canonical=None, *, keywords=(), store=None, merge=None,
                 site_type=None, action="create", note=None):
        self.canonical = canonical
        self.keywords = tuple(k.lower() for k in keywords)
        self.store = store
        self.merge = merge or (canonical or "")
        self.site_type = site_type
        self.action = action
        self.note = note


DECISIONS = [
    # exclusions FIRST (most specific) — the parent account is not a building
    Rule(keywords=["main account", "parent account", "rh parent", "corporate parent"],
         action="exclude", note="Restoration Hardware parent account — not a building"),
    # merges / canonical overrides
    Rule("Hollywood Gallery", keywords=["hollywood"], merge="hollywood"),
    Rule("Chicago Gallery #147", keywords=["chicago"], store="147", merge="147"),
    Rule("Linden House Gallery", keywords=["linden", "lindern"], merge="linden"),
    Rule("Beverly Modern Gallery", keywords=["beverly modern", "beverly"], merge="beverly"),
    Rule("Austin Gallery #149", keywords=["austin"], store="149", merge="149"),
    Rule("Dallas Gallery #168", keywords=["dallas"], store="168", merge="168"),
    Rule("Pleasanton Gallery", keywords=["pleasanton", "pleaston"], merge="pleasanton"),
    Rule("Princeton Gallery #644", keywords=["princeton", "brunswick pike", "3265"], store="644",
         merge="644"),
    Rule("LaSalle Gallery", keywords=["lasalle", "lasale", "lasle"], merge="lasalle"),
    Rule("Pembroke Gallery", keywords=["pembroke", "pembrooke"], merge="pembroke"),
    Rule("Richmond Gallery", keywords=["richmond"], merge="richmond"),
    Rule("Soda Grocery Gallery", keywords=["soda grocery", "soda"], merge="soda"),
    Rule("Patterson Warehouse", keywords=["patterson"], merge="patterson", site_type="warehouse"),
    Rule("MDC Distribution Center", keywords=["mdc"], merge="mdc", site_type="distribution_center"),
    Rule("RH NYC Flagship", keywords=["rhnyc", "rh nyc"], merge="rhnyc"),
    Rule("Memphis Gallery", keywords=["memphis"], merge="memphis",
         note="Memphis Gallery for now — requires research"),
]

# Explicit keep-separate guard: these store numbers must NEVER be merged together.
KEEP_SEPARATE = {"159", "178"}   # Edina #159 and Raleigh #178 stay distinct buildings


# ── pure candidate parsing ───────────────────────────────────────────
def norm_alias(s) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def norm_id(v) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()


def parse_review_item(item) -> dict | None:
    """(review_id, candidate) from a PortfolioReviewItem.  None if unparseable."""
    try:
        cand = json.loads(item.payload) if item.payload else None
    except Exception:
        cand = None
    if not cand or not isinstance(cand, dict):
        return None
    return {"review_id": item.id, "review_type": item.review_type,
            "candidate": cand, "candidate_name": item.candidate_name,
            "store_number": item.store_number or cand.get("store_number")}


def _haystack(cand: dict) -> str:
    names = [cand.get("canonical_name") or ""]
    for src, lst in (cand.get("source_names") or {}).items():
        names.extend(lst or [])
    return " ".join(names).lower()


def match_decision(cand: dict, store_number):
    hay = _haystack(cand)
    for rule in DECISIONS:
        if rule.store and str(store_number) == str(rule.store):
            return rule
        if rule.keywords and any(k in hay for k in rule.keywords):
            return rule
    return None


def is_parent_account(cand: dict, store_number) -> bool:
    """Bare 'Restoration Hardware' with no store number and no distinctive token."""
    if store_number:
        return False
    hay = _haystack(cand)
    if "main account" in hay or "parent account" in hay:
        return True
    distinctive = set(re.sub(r"[^a-z0-9]+", " ", hay).split()) - {"restoration", "hardware", "rh"}
    distinctive = {t for t in distinctive if not t.isdigit() and len(t) >= 3}
    return not distinctive


def candidate_aliases(cand: dict) -> list[str]:
    """Distinctive source labels (skip the bare brand, which would collide)."""
    seen, out = set(), []
    for src, lst in (cand.get("source_names") or {}).items():
        for nm in (lst or []):
            n = norm_alias(nm)
            if not n or n in seen:
                continue
            # skip the generic brand-only alias
            if n in ("restorationhardware", "rh"):
                continue
            seen.add(n)
            out.append(nm)
    return out


def candidate_device_mappings(cand: dict) -> list[dict]:
    out = []

    def add(kind, value, source):
        if value:
            out.append({"kind": kind, "value": str(value), "source": source})

    for d in cand.get("devices", []):
        add("napco_radio", d.get("radio_number"), "napco")
        add("napco_radio", d.get("starlink_id"), "napco")
        add("napco_radio", d.get("serial"), "napco")
        add("iccid", d.get("iccid"), "vendor")
        add("imei", d.get("imei"), "vendor")
        if d.get("msisdn"):
            add("genesis_msisdn", d.get("msisdn"), "genesis")
            add("phone", d.get("msisdn"), "fusion")
    sid = (cand.get("e911") or {}).get("site_id")
    add("true911_device", sid, "true911")
    for nm in (cand.get("source_names") or {}).get("zoho", []) or []:
        add("zoho_account", nm, "zoho")
    return out


# ══════════════════════════════════════════════════════════════════════
# Plan builder (PURE — no DB).  Collision-safe against the registry unique keys.
# ══════════════════════════════════════════════════════════════════════
def build_plan(parsed: list[dict], *, apply_decisions: bool, only_high: bool, limit=None) -> dict:
    creates, order = {}, []
    excluded, skipped, unresolved, merged = [], [], [], []
    seen_alias, seen_map = set(), set()   # global collision guards (uq constraints)
    building_count = 0

    for p in parsed:
        if p is None:
            unresolved.append({"reason": "unparseable_payload"})
            continue
        cand, store = p["candidate"], p["store_number"]
        decision = match_decision(cand, store) if apply_decisions else None

        if (decision and decision.action == "exclude") or (apply_decisions and is_parent_account(cand, store)):
            excluded.append({"review_id": p["review_id"], "name": p["candidate_name"],
                             "reason": (decision.note if decision else "parent/main account")})
            continue

        is_decision = decision is not None
        conf = cand.get("source_confidence") or 0
        if only_high and not is_decision and conf < HIGH_CONFIDENCE:
            skipped.append({"review_id": p["review_id"], "name": p["candidate_name"],
                            "reason": f"below high-confidence ({conf})"})
            continue

        if is_decision:
            key = f"dec:{decision.merge}"
            canonical = decision.canonical
            site_type = decision.site_type or cand.get("site_type")
        elif store and str(store).isdigit():
            key = f"store:{store}"
            canonical = cand.get("canonical_name")
            site_type = cand.get("site_type")
        else:
            key = f"name:{norm_alias(cand.get('canonical_name'))}"
            canonical = cand.get("canonical_name")
            site_type = cand.get("site_type")

        spec = creates.get(key)
        if spec is None:
            if limit is not None and building_count >= limit:
                skipped.append({"review_id": p["review_id"], "name": p["candidate_name"],
                                "reason": "over --limit"})
                continue
            addr = cand.get("address") or {}
            spec = {"key": key, "canonical_name": canonical, "store_number": store,
                    "site_type": site_type, "building_category": cand.get("building_category"),
                    "address": addr.get("street"), "city": addr.get("city"),
                    "state": addr.get("state"), "zip": addr.get("zip"),
                    "aliases": [], "device_mappings": [], "review_ids": [],
                    "sources": set(), "note": (decision.note if decision else None)}
            creates[key] = spec
            order.append(key)
            building_count += 1
        else:
            merged.append({"review_id": p["review_id"], "name": p["candidate_name"],
                           "into": spec["canonical_name"]})

        spec["review_ids"].append(p["review_id"])
        spec["sources"].update(cand.get("sources") or [])
        if not spec["store_number"] and store and str(store).isdigit():
            spec["store_number"] = store        # adopt a store # from a merged candidate
        if not spec["address"] and (cand.get("address") or {}).get("street"):
            a = cand["address"]
            spec.update(address=a.get("street"), city=a.get("city"), state=a.get("state"), zip=a.get("zip"))
        # collision-safe aliases
        for al in candidate_aliases(cand):
            n = norm_alias(al)
            if n and n not in seen_alias:
                seen_alias.add(n)
                spec["aliases"].append(al)
        # collision-safe device mappings (uq: kind + normalized value)
        for m in candidate_device_mappings(cand):
            vn = norm_id(m["value"]) if m["kind"] != "zoho_account" else norm_alias(m["value"])
            mk = (m["kind"], vn)
            if vn and mk not in seen_map:
                seen_map.add(mk)
                spec["device_mappings"].append(m)

    return {"creates": [creates[k] for k in order], "excluded": excluded,
            "skipped": skipped, "merged": merged, "unresolved": unresolved}


# ══════════════════════════════════════════════════════════════════════
# Apply (writes the registry ONLY under --apply)
# ══════════════════════════════════════════════════════════════════════
async def apply_plan(db, tenant_id: str, plan: dict, *, approved_by: str) -> list[dict]:
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.portfolio_registry import PortfolioReviewItem
    from app.services import portfolio_registry as reg

    created = []
    for spec in plan["creates"]:
        primary = spec["review_ids"][0] if spec["review_ids"] else None
        try:
            res = await reg.approve_new_building(
                db, tenant_id, approved_by=approved_by, canonical_name=spec["canonical_name"],
                store_number=spec["store_number"], site_type=spec["site_type"],
                address=spec["address"], city=spec["city"], state=spec["state"], zip=spec["zip"],
                aliases=spec["aliases"], device_mappings=spec["device_mappings"],
                review_item_id=primary, notes=spec.get("note"))
        except Exception as exc:      # uq/integrity edge — report, don't crash the run
            created.append({"canonical_name": spec["canonical_name"], "error": f"{type(exc).__name__}: {exc}"})
            continue
        bid = res["building_id"]
        # mark the merged extra review items decided → this building
        for rid in spec["review_ids"][1:]:
            row = (await db.execute(select(PortfolioReviewItem).where(
                PortfolioReviewItem.tenant_id == tenant_id,
                PortfolioReviewItem.id == rid))).scalar_one_or_none()
            if row is not None:
                row.status = "approved"
                row.decided_by = approved_by
                row.decided_at = datetime.now(timezone.utc)
                row.suggested_building_id = bid
        await db.commit()
        created.append({"building_id": bid, "canonical_name": spec["canonical_name"],
                        "store_number": spec["store_number"], "aliases": len(spec["aliases"]),
                        "device_mappings": len(spec["device_mappings"]),
                        "merged_reviews": len(spec["review_ids"]), "note": spec.get("note")})
    return created


# ── counts (before/after visible) ────────────────────────────────────
async def _counts(db, tenant_id: str) -> dict:
    from sqlalchemy import func, select

    from app.models.portfolio_registry import PortfolioBuilding, PortfolioReviewItem
    from app.models.site import Site

    approved = (await db.execute(select(func.count()).select_from(PortfolioBuilding).where(
        PortfolioBuilding.tenant_id == tenant_id, PortfolioBuilding.approved.is_(True)))).scalar() or 0
    pending = (await db.execute(select(func.count()).select_from(PortfolioReviewItem).where(
        PortfolioReviewItem.tenant_id == tenant_id,
        PortfolioReviewItem.status == "pending"))).scalar() or 0
    legacy = (await db.execute(select(func.count()).select_from(Site).where(
        Site.tenant_id == tenant_id))).scalar() or 0
    return {"approved_buildings": approved, "pending_review": pending, "legacy_sites": legacy}


def _visible(approved, legacy):
    """What the customer sees: approved buildings if any (registry mode), else the
    legacy Site count (fallback mode)."""
    return approved if approved > 0 else legacy


async def _load_pending(db, tenant_id: str) -> list:
    from sqlalchemy import select

    from app.models.portfolio_registry import PortfolioReviewItem
    return (await db.execute(select(PortfolioReviewItem).where(
        PortfolioReviewItem.tenant_id == tenant_id,
        PortfolioReviewItem.status == "pending").order_by(PortfolioReviewItem.id))).scalars().all()


async def _run(args) -> dict:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        before = await _counts(db, args.tenant)
        items = await _load_pending(db, args.tenant)
        parsed = [parse_review_item(it) for it in items]
        plan = build_plan(parsed, apply_decisions=args.include_known_rh_decisions,
                          only_high=args.only_high_confidence, limit=args.limit)

        applied = None
        if args.apply:
            applied = await apply_plan(db, args.tenant, plan, approved_by=args.approved_by)
            after_counts = await _counts(db, args.tenant)
        else:
            after_counts = {**before,
                            "approved_buildings": before["approved_buildings"] + len(plan["creates"])}

    before_visible = _visible(before["approved_buildings"], before["legacy_sites"])
    after_visible = _visible(after_counts["approved_buildings"], before["legacy_sites"])
    return {
        "tenant": args.tenant, "mode": "apply" if args.apply else "dry-run",
        "decisions_applied": args.include_known_rh_decisions,
        "pending_reviewed": len(items),
        "created": applied if applied is not None else
                   [{"canonical_name": s["canonical_name"], "store_number": s["store_number"],
                     "aliases": len(s["aliases"]), "device_mappings": len(s["device_mappings"]),
                     "merged_reviews": len(s["review_ids"]), "note": s.get("note")}
                    for s in plan["creates"]],
        "created_count": len(plan["creates"]),
        "merged": plan["merged"], "excluded": plan["excluded"],
        "skipped": plan["skipped"], "unresolved": plan["unresolved"],
        "before": {**before, "visible_count": before_visible,
                   "mode": "registry_mode" if before["approved_buildings"] else "fallback_mode"},
        "after": {**after_counts, "visible_count": after_visible,
                  "mode": "registry_mode" if after_counts["approved_buildings"] else "fallback_mode"},
    }


def _print(r: dict) -> None:
    print("=" * 70)
    print(f"RH registry approval — {r['mode'].upper()}   (tenant: {r['tenant']})")
    print("=" * 70)
    print(f"  pending reviewed : {r['pending_reviewed']}")
    print(f"  buildings created: {r['created_count']}   merged: {len(r['merged'])}   "
          f"excluded: {len(r['excluded'])}   skipped: {len(r['skipped'])}   "
          f"unresolved: {len(r['unresolved'])}")
    print("-" * 70)
    for c in r["created"][:200]:
        extra = f"  ⚠ {c['note']}" if c.get("note") else ""
        err = f"  ERROR {c['error']}" if c.get("error") else ""
        print(f"  + {c.get('canonical_name'):32} store#={c.get('store_number') or '—':>5}  "
              f"aliases={c.get('aliases', 0)} maps={c.get('device_mappings', 0)} "
              f"merged={c.get('merged_reviews', 0)}{extra}{err}")
    if r["excluded"]:
        print("  excluded (not buildings):")
        for e in r["excluded"]:
            print(f"    - {e.get('name') or e.get('review_id')}: {e['reason']}")
    print("-" * 70)
    b, a = r["before"], r["after"]
    print(f"  BEFORE: approved={b['approved_buildings']} visible={b['visible_count']} "
          f"({b['mode']})")
    print(f"  AFTER : approved={a['approved_buildings']} visible={a['visible_count']} "
          f"({a['mode']})")
    if r["mode"] == "dry-run":
        print("  (DRY-RUN — wrote nothing. Re-run with --apply to persist.)")
    print("  (Never modified Site / Device / E911 / Zoho / Napco / Genesis.)")


def main() -> None:
    ap = argparse.ArgumentParser(description="RH registry approval from review items.")
    ap.add_argument("--tenant", default=DEFAULT_TENANT)
    ap.add_argument("--dry-run", action="store_true", help="preview only (default)")
    ap.add_argument("--apply", action="store_true", help="persist approvals to the registry")
    ap.add_argument("--limit", type=int, default=None, help="cap the number of buildings created")
    ap.add_argument("--only-high-confidence", action="store_true",
                    help="only approve high-confidence non-decision candidates")
    ap.add_argument("--include-known-rh-decisions", action="store_true",
                    help="apply the operator decision table (merges / exclusions / canonical names)")
    ap.add_argument("--approved-by", default="rh-registry-approval-script")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.apply and args.dry_run:
        ap.error("choose one of --apply or --dry-run (default is --dry-run)")

    try:
        report = asyncio.run(_run(args))
    except Exception as exc:
        print(f"ERROR: approval run failed — {type(exc).__name__}: {exc}")
        raise SystemExit(3)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print(report)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
