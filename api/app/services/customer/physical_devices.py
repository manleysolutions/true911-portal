"""Physical-device counting for a canonical building (PURE — no DB).

A building's "Devices" KPI must count PHYSICAL service devices — a Napco
StarLink radio, an MS130v4, a True911-managed communicator — exactly once each.
Identifiers are not devices: an ICCID (the SIM), an IMEI, an MSISDN and a
telephone number all *describe* a device or a connection, and one physical
device routinely carries several of them.  Counting identifiers inflates the
KPI; counting only True911 ``Device`` rows under-counts buildings whose
equipment is known only through approved registry mappings (the RH
"Devices = 0" defect).

Method: union-find over normalized identifiers.  Every evidence source
contributes a GROUP of identifiers that belong to one thing, flagged as a
physical ANCHOR or not:

  * approved registry mappings — ``napco_radio`` and ``imei`` values are
    anchors (each names one physical unit); ``iccid`` / ``genesis_msisdn`` /
    ``phone`` are identifiers that attach to an anchor when linked, and never
    count on their own.  ``true911_device`` (a site id) and ``zoho_account``
    (an account label) are not device identifiers and are ignored.
  * fused device records (the review-queue payload the building was approved
    from) — one fused device = one group, already merged across sources by the
    Fusion Engine; an anchor unless it is a bare ``line``.
  * True911 ``Device`` rows on the building's linked sites — one row = one
    physical anchor, grouped with its own IMEI / ICCID / MSISDN / serial.

Groups sharing any identifier merge.  The count is the number of merged
components that contain at least one anchor — so a radio seen in Napco, Zoho
and True911 with its SIM and number is ONE device, and a lone ICCID or phone
number is zero devices.
"""

from __future__ import annotations

import re
from typing import Iterable

ANCHOR_MAPPING_KINDS = frozenset({"napco_radio", "imei"})
IDENTIFIER_MAPPING_KINDS = frozenset({"iccid", "genesis_msisdn", "phone"})
NON_DEVICE_FUSED_KINDS = frozenset({"line"})
_FUSED_ID_FIELDS = ("radio_number", "starlink_id", "serial", "imei", "iccid", "msisdn")


def norm_identifier(v) -> str:
    """Join-key normalization shared with the registry (alnum, upper-cased)."""
    return re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()


def norm_phone(v) -> str | None:
    """A 10-digit NANP number (leading country code dropped), else None."""
    digits = re.sub(r"\D", "", str(v or ""))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _clean(ids: Iterable) -> list[str]:
    return [n for n in (norm_identifier(i) for i in ids) if n]


def mapping_groups(mappings: Iterable) -> list[tuple[list[str], bool]]:
    """Registry mappings → (identifiers, is_anchor) groups.  Accepts ORM rows or
    dicts with ``kind`` / ``value`` / ``active``."""
    out = []
    for m in mappings:
        get = m.get if isinstance(m, dict) else (lambda k, _m=m: getattr(_m, k, None))
        if get("active") is False:
            continue
        kind = get("kind")
        if kind in ANCHOR_MAPPING_KINDS:
            ids = _clean([get("value")])
            if ids:
                out.append((ids, True))
        elif kind in IDENTIFIER_MAPPING_KINDS:
            ids = _clean([get("value")])
            if ids:
                out.append((ids, False))
    return out


def fused_device_groups(devices: Iterable[dict]) -> list[tuple[list[str], bool]]:
    """Fused device records (from a review payload) → groups."""
    out = []
    for d in devices or []:
        if not isinstance(d, dict):
            continue
        ids = _clean(d.get(f) for f in _FUSED_ID_FIELDS)
        if ids:
            out.append((ids, (d.get("kind") or "device") not in NON_DEVICE_FUSED_KINDS))
    return out


def site_device_groups(devices: Iterable) -> list[tuple[list[str], bool]]:
    """True911 ``Device`` rows → one anchor group each (keyed by its own id so a
    row with no shared identifier still counts once)."""
    out = []
    for d in devices or []:
        ids = _clean([getattr(d, "imei", None), getattr(d, "iccid", None),
                      getattr(d, "msisdn", None), getattr(d, "serial_number", None)])
        ids.append("T911DEV:" + norm_identifier(getattr(d, "device_id", None) or id(d)))
        out.append((ids, True))
    return out


def count_physical_devices(groups: Iterable[tuple[list[str], bool]]) -> int:
    """Number of merged identifier components that contain a physical anchor."""
    uf = _UnionFind()
    anchors: set[str] = set()
    for ids, is_anchor in groups:
        if not ids:
            continue
        first = ids[0]
        uf.find(first)
        for other in ids[1:]:
            uf.union(first, other)
        if is_anchor:
            anchors.add(first)
    return len({uf.find(a) for a in anchors})


def relevant_fused_groups(building_ids: set[str], fused: Iterable[tuple[list[str], bool]]):
    """Only the fused-device groups that share an identifier with the building's
    own evidence — so a tenant-wide payload pool never leaks devices across
    buildings."""
    return [(ids, anchor) for ids, anchor in fused if any(i in building_ids for i in ids)]


def building_physical_devices(mappings, site_devices=(), fused_groups=()) -> int:
    """Physical-device count for ONE building from all its evidence."""
    own = mapping_groups(mappings) + site_device_groups(site_devices)
    own_ids = {i for ids, _a in own for i in ids}
    return count_physical_devices(own + relevant_fused_groups(own_ids, fused_groups))


def building_phone_numbers(mappings, service_phones=()) -> list[str]:
    """Distinct 10-digit connection numbers from registry ``phone`` mappings + the
    phone numbers already on the building's services (deduplicated).  A
    ``genesis_msisdn`` mapping is a SIM MSISDN, never a customer telephone
    number (CG-1 L3)."""
    nums: set[str] = set()
    for m in mappings or []:
        get = m.get if isinstance(m, dict) else (lambda k, _m=m: getattr(_m, k, None))
        if get("active") is False or get("kind") != "phone":
            continue
        p = norm_phone(get("value"))
        if p:
            nums.add(p)
    for ph in service_phones or []:
        p = norm_phone(ph)
        if p:
            nums.add(p)
    return sorted(nums)
