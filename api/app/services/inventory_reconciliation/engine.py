"""Reconciliation engine — pure, vendor- and customer-agnostic.

reconcile(vendor_records, true911_items) -> (rows, summary)

Matching hierarchy (strongest first):
  1. ICCID exact            confidence 1.0
  2. RadioNumber exact      confidence 0.9
  3. SubscriberName norm    confidence 0.6  -> REVIEW (name alone is weak)
  4. Site/address overlap   confidence ~0.4 -> REVIEW

Result:
  MATCHED            strong-key match AND full True911 linkage (site + service unit)
  PARTIAL            strong-key match but missing site/service-unit linkage
  MISSING_IN_TRUE911 vendor radio has no True911 device
  MISSING_IN_VENDOR  True911 device not present in the vendor export (reverse pass)
  DUPLICATE          ICCID dup in vendor export, or key matches >1 True911 device
  REVIEW             only a weak (name/site) match — needs a human
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from app.services.inventory_reconciliation import normalize as N
from app.services.inventory_reconciliation.models import ReconRow, Result, True911Item, VendorRecord

_NAME_EXACT_CONF = 0.6
_SITE_THRESHOLD = 0.5


def _derive_customer(rec: VendorRecord):
    if rec.customer_hint:
        return rec.customer_hint
    name = rec.subscriber_name
    if not name:
        return None
    # Generic: the leading words before the first number / '#' usually name the
    # customer (e.g. "<Customer> #351 ..."). No hardcoded customer string.
    head = re.split(r"[#0-9]", name, maxsplit=1)[0].strip()
    return head or name.strip()


def _base(v: VendorRecord) -> dict:
    return dict(customer=_derive_customer(v), site=v.site_hint or v.subscriber_name,
                radio_number=v.radio_number, iccid=v.iccid, subscriber_name=v.subscriber_name)


def _strong_row(base, it: True911Item, conf, basis):
    full = bool(it.site_id and it.service_unit_id)
    gaps = []
    if not it.site_id:
        gaps.append("no site")
    if not it.service_unit_id:
        gaps.append("no service unit")
    if (it.e911_status or "").lower() not in ("validated", "verified"):
        gaps.append("E911 not verified")
    notes = f"matched by {basis}" + (("; " + ", ".join(gaps)) if gaps else "")
    row = ReconRow(**base, true911_device_id=it.device_id, true911_site=it.site_name,
                   true911_customer=it.customer_name, service_unit_id=it.service_unit_id,
                   e911_status=it.e911_status, last_telemetry=it.last_telemetry,
                   confidence=conf,
                   result=(Result.MATCHED.value if full else Result.PARTIAL.value), notes=notes)
    return row, [it.device_id]


def _review_row(base, it: True911Item, conf, basis):
    row = ReconRow(**base, true911_device_id=it.device_id, true911_site=it.site_name,
                   true911_customer=it.customer_name, service_unit_id=it.service_unit_id,
                   e911_status=it.e911_status, last_telemetry=it.last_telemetry,
                   confidence=conf, result=Result.REVIEW.value, notes=f"weak match by {basis} — review")
    return row, [it.device_id]


def _dup_row(base, cands, why):
    ids = ",".join(c.device_id for c in cands)
    row = ReconRow(**base, true911_device_id=ids, true911_site=None, true911_customer=None,
                   service_unit_id=None, e911_status=None, last_telemetry=None,
                   confidence=1.0, result=Result.DUPLICATE.value, notes=f"{why}: {ids}")
    return row, [c.device_id for c in cands]


def _missing_in_true911(base, why):
    row = ReconRow(**base, true911_device_id=None, true911_site=None, true911_customer=None,
                   service_unit_id=None, e911_status=None, last_telemetry=None,
                   confidence=0.0, result=Result.MISSING_IN_TRUE911.value, notes=why)
    return row, []


def _missing_in_vendor(it: True911Item) -> ReconRow:
    return ReconRow(customer=it.customer_name, site=it.site_name, radio_number=it.radio_number,
                    iccid=it.iccid, subscriber_name=None, true911_device_id=it.device_id,
                    true911_site=it.site_name, true911_customer=it.customer_name,
                    service_unit_id=it.service_unit_id, e911_status=it.e911_status,
                    last_telemetry=it.last_telemetry, confidence=0.0,
                    result=Result.MISSING_IN_VENDOR.value,
                    notes="In True911 inventory but not in the vendor export")


def reconcile(vendor_records, true911_items):
    by_iccid = defaultdict(list)
    by_radio = defaultdict(list)
    name_index = []  # (normalized "customer site", item)
    for it in true911_items:
        ic = N.norm_iccid(it.iccid)
        if ic:
            by_iccid[ic].append(it)
        rn = N.norm_radio(it.radio_number)
        if rn:
            by_radio[rn].append(it)
        name_index.append((N.norm_name(f"{it.customer_name or ''} {it.site_name or ''}"), it))

    vendor_iccid_counts = Counter(N.norm_iccid(v.iccid) for v in vendor_records if N.norm_iccid(v.iccid))

    rows = []
    matched_ids = set()
    for v in vendor_records:
        base = _base(v)
        ic = N.norm_iccid(v.iccid)
        rn = N.norm_radio(v.radio_number)
        vn = N.norm_name(v.subscriber_name)

        # vendor-side duplicate ICCID
        if ic and vendor_iccid_counts.get(ic, 0) > 1:
            row = ReconRow(**base, true911_device_id=None, true911_site=None, true911_customer=None,
                           service_unit_id=None, e911_status=None, last_telemetry=None,
                           confidence=1.0, result=Result.DUPLICATE.value,
                           notes=f"ICCID appears {vendor_iccid_counts[ic]}x in the vendor export")
            rows.append(row)
            continue

        # 1. ICCID exact
        if ic and ic in by_iccid:
            cands = by_iccid[ic]
            row, ids = (_dup_row(base, cands, "ICCID matches multiple True911 devices")
                        if len(cands) > 1 else _strong_row(base, cands[0], 1.0, "ICCID"))
        # 2. RadioNumber exact
        elif rn and rn in by_radio:
            cands = by_radio[rn]
            row, ids = (_dup_row(base, cands, "RadioNumber matches multiple True911 devices")
                        if len(cands) > 1 else _strong_row(base, cands[0], 0.9, "RadioNumber"))
        # 3. SubscriberName normalized exact
        elif vn and (exact := [it for nm, it in name_index if nm and nm == vn]):
            row, ids = (_dup_row(base, exact, "SubscriberName matches multiple True911 devices")
                        if len(exact) > 1 else _review_row(base, exact[0], _NAME_EXACT_CONF, "SubscriberName"))
        else:
            # 4. Site/address similarity (weakest)
            best, best_score = None, 0.0
            for nm, it in name_index:
                sc = N.site_similarity(v.site_hint or v.subscriber_name,
                                       f"{it.customer_name or ''} {it.site_name or ''}")
                if sc > best_score:
                    best, best_score = it, sc
            if best and best_score >= _SITE_THRESHOLD:
                row, ids = _review_row(base, best, round(0.4 * best_score + 0.2, 2),
                                       f"site similarity {best_score:.2f}")
            else:
                row, ids = _missing_in_true911(base, "No True911 device matched this vendor radio")

        rows.append(row)
        matched_ids.update(ids)

    # Reverse pass: True911 devices not referenced by any vendor record.
    for it in true911_items:
        if it.device_id not in matched_ids:
            rows.append(_missing_in_vendor(it))

    return rows, summarize(rows)


def summarize(rows) -> dict:
    c = Counter(r.result for r in rows)
    total = len(rows)
    vendor_seen = sum(1 for r in rows if r.result != Result.MISSING_IN_VENDOR.value)
    return {
        "total_rows": total,
        "vendor_records": vendor_seen,
        "by_result": dict(c),
        "matched": c.get("MATCHED", 0),
        "partial": c.get("PARTIAL", 0),
        "missing_in_true911": c.get("MISSING_IN_TRUE911", 0),
        "missing_in_vendor": c.get("MISSING_IN_VENDOR", 0),
        "duplicate": c.get("DUPLICATE", 0),
        "review": c.get("REVIEW", 0),
        "match_rate": round(c.get("MATCHED", 0) / vendor_seen, 3) if vendor_seen else 0.0,
    }
