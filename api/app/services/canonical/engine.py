"""Canonical reconciliation engine - PURE (no DB, no I/O).  DECISIONS D-023.

``project(snapshot)`` turns a read-only snapshot of every source into:

  * communications ASSETS (telephone numbers, NAPCO radios, SIMs, IMEIs), each
    with a placement (building + confidence + basis) and a lifecycle;
  * life-safety SERVICES (FACP / ELEVATOR / EMERGENCY_PHONE, plus UNCLASSIFIED
    telephone services that are reported but never counted);
  * REQUIRED CONNECTIONS - generated only for services that are CONFIRMED (or
    operator-APPROVED), not operator-REJECTED and CURRENT: ELEVATOR and
    EMERGENCY_PHONE require 1, FACP requires 2.  A connection is a required path,
    not a telephone number; no number is ever fabricated for an FACP path;
  * FINDINGS for operator review, per-building and portfolio SUMMARIES, and a
    strict report for every building an operator marked
    BUILDING_IDENTITY_SUSPECT (e.g. a building historically merged with others).

Placement priority (strongest first): operator decision; exact asset
identifier; exact telephone mapping; building-specific facility name; unique
store number; exact normalised address; specific account alias.  A historical
site link or a generic / parent-account name is SUPPORTING evidence only and
never places a record on its own.  For a suspect building, the registry's own
aliases / mappings / site links are demoted to supporting evidence as well:
only the building's intrinsic identity (canonical name, store number, address)
or an operator decision can place a record there.

Confidence, approval, lifecycle and DEPLOYMENT stay separate.  PROBABLE /
UNRESOLVED never become CONFIRMED here.  An administrative status (Zoho
"Activated", a True911 or carrier "active") never makes anything CURRENT.
DEPLOYED needs BOTH (a) liveness - an operator lifecycle decision, recent True911
telemetry or recent NAPCO / T-Mobile activity in an imported snapshot - AND (b)
deterministic placement at that building (operator placement or an exact
registry identifier / telephone mapping).  Activity proves the equipment is
alive, never where it is.  Negative statuses (de-activated / suspended) are
still honoured.  E911 is not an input or an output of this engine.

Snapshot shape (all lists of plain dicts): see ``loader.build_snapshot``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from app.services.canonical import vocab as V
from app.services.canonical.normalize import (
    classify_label,
    is_sku_label,
    mask,
    n10,
    naddr,
    nalias,
    nid,
    radio_id,
    source_lifecycle,
    store_number,
    words,
)

_PREFIX = {V.FACP: "FACP", V.ELEVATOR: "ELEV", V.EMERGENCY_PHONE: "EPH",
           V.UNCLASSIFIED: "UNCL"}
_DISPLAY = {V.FACP: "Fire alarm panel", V.ELEVATOR: "Elevator",
            V.EMERGENCY_PHONE: "Emergency phone", V.UNCLASSIFIED: "Telephone line"}
_INFERRED = {"Elevator": V.ELEVATOR, "Emergency Phone": V.EMERGENCY_PHONE,
             "Area of Refuge": V.EMERGENCY_PHONE, "Fire Alarm": V.FACP}


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _asset_key(atype: str, value: str) -> str:
    return "%s:%s" % (atype, value)


def _display(atype: str, value: str) -> str:
    return mask(value) if atype in V.MASKED_ASSET_TYPES else value


# ─────────────────────────────────────────────────────────── decisions ──

def interpret_decisions(decisions: list[dict]) -> dict:
    """Active operator decisions -> the lookups the engine applies."""
    out = {"suspect": set(), "lifecycle": {}, "place": {}, "classify": {},
           "approval": {}, "events": [], "facp_groups": [], "records": {}, "pools": [],
           "place_asset": {}}
    ordered = sorted(decisions, key=lambda d: 1 if d["decision_type"] == V.D_ASSET_LIFECYCLE else 0)
    for d in ordered:
        t, s, ns = d["decision_type"], d["subject"], d["new_state"]
        eff = d.get("effective_date")
        if t == V.D_BUILDING_IDENTITY_SUSPECT:
            if ns.get("suspect"):
                out["suspect"].add(s["building_id"])
        elif t == V.D_CARRIER_MIGRATION:
            bid = s["building_id"]
            out["events"].append({"decision_key": d["decision_key"], "decision_id": d.get("id"),
                                  "building_id": bid, "event_type": V.REASON_CARRIER_MIGRATION,
                                  "effective_at": eff, "reason": d.get("reason"),
                                  "legacy": s["legacy_numbers"],
                                  "replacement": s["replacement_numbers"]})
            for n in s["legacy_numbers"]:
                out["lifecycle"][_asset_key(V.TELEPHONE_NUMBER, n)] = {
                    "lifecycle": ns["legacy_lifecycle"], "reason": V.REASON_CARRIER_MIGRATION,
                    "effective_to": eff, "carrier": ns.get("legacy_carrier"),
                    "event_key": d["decision_key"]}
                out["place"][n] = bid
            for n in s["replacement_numbers"]:
                out["lifecycle"][_asset_key(V.TELEPHONE_NUMBER, n)] = {
                    "lifecycle": ns["replacement_lifecycle"], "reason": V.REASON_CARRIER_MIGRATION,
                    "effective_from": eff, "carrier": ns.get("replacement_carrier"),
                    "event_key": d["decision_key"]}
                out["place"][n] = bid
        elif t == V.D_ASSET_LIFECYCLE:
            key = _asset_key(s["asset_type"], s["value"])
            prev = out["lifecycle"].get(key, {})
            out["lifecycle"][key] = dict(prev, lifecycle=ns["lifecycle"],
                                         reason=ns.get("reason") or V.REASON_OPERATOR)
        elif t == V.D_SERVICE_CLASSIFICATION:
            out["classify"][s["number"]] = (ns["service_type"], ns.get("label"))
            out["place"][s["number"]] = s["building_id"]
        elif t == V.D_SERVICE_APPROVAL:
            out["approval"][(s["building_id"], s["service_key"])] = ns["approval"]
        elif t == V.D_FACP_SERVICE:
            out["facp_groups"].append({"building_id": s["building_id"], "ref": s["service_ref"],
                                       "radios": list(ns["radios"]), "label": ns.get("label"),
                                       "decision_key": d["decision_key"]})
        elif t == V.D_SOURCE_RECORD:
            prefix = "zoho:" if s["source"] == V.SRC_ZOHO else "device:"
            out["records"][prefix + s["record_id"]] = dict(ns, decision_key=d["decision_key"])
        elif t == V.D_SERVICE_POOL:
            out["pools"].append({"building_id": s["building_id"], "ref": s["pool_ref"],
                                 "numbers": list(ns["numbers"]),
                                 "service_types": list(ns["service_types"]),
                                 "label": ns.get("label"), "decision_key": d["decision_key"]})
    # a radio claimed by two FACP_SERVICE decisions is a conflict: neither applies
    claims = Counter(r for g in out["facp_groups"] for r in g["radios"])
    out["group_conflicts"] = sorted(r for r, c in claims.items() if c > 1)
    out["facp_groups"] = [g for g in out["facp_groups"]
                          if not set(g["radios"]) & set(out["group_conflicts"])]
    for g in out["facp_groups"]:
        for r in g["radios"]:
            out["place_asset"][_asset_key(V.NAPCO_RADIO, r)] = g["building_id"]
    for pool in out["pools"]:               # explicit per-number decisions win
        for n in pool["numbers"]:
            out["place"].setdefault(n, pool["building_id"])
    return out


# ──────────────────────────────────────────────────────────── indexes ──

class _Index:
    def __init__(self, snap: dict, suspect: set):
        self.buildings = {b["id"]: b for b in snap.get("buildings") or []}
        self.suspect = suspect
        self.alias = defaultdict(set)          # key -> {(bid, intrinsic)}
        self.store = defaultdict(set)
        self.addr = defaultdict(set)
        self.number = defaultdict(set)         # registry telephone mappings
        self.ident = defaultdict(set)          # registry NAPCO / ICCID / IMEI
        self.site_map = defaultdict(set)       # site_id -> {bid}
        for b in self.buildings.values():
            if nalias(b.get("name")):
                self.alias[nalias(b["name"])].add((b["id"], True))
            st = str(b.get("store_number") or "").lstrip("0")
            if st:
                self.store[st.upper()].add(b["id"])
            a = naddr(b.get("address"), b.get("city"), b.get("state"))
            if a:
                self.addr[a].add(b["id"])
        for a in snap.get("aliases") or []:
            if a["building_id"] in self.buildings and nalias(a.get("alias")):
                self.alias[nalias(a["alias"])].add((a["building_id"], False))
        for m in snap.get("mappings") or []:
            bid, kind, val = m["building_id"], m["kind"], m.get("value")
            if bid not in self.buildings:
                continue
            if kind == "zoho_account" and nalias(val):
                self.alias[nalias(val)].add((bid, False))
            elif kind in ("phone", "genesis_msisdn") and n10(val):
                self.number[n10(val)].add(bid)
            elif kind in ("napco_radio", "iccid", "imei") and nid(val):
                self.ident[nid(val)].add(bid)
            elif kind == "true911_device" and val:
                self.site_map[str(val)].add(bid)
        generic = {nalias(z.get("parent")) for z in snap.get("zoho_rows") or [] if z.get("parent")}
        generic |= {nalias(g) for g in snap.get("generic_names") or []}
        self.generic = {g for g in generic if g}


def _hits(ix: _Index, rec: dict) -> list[tuple]:
    """Every placement hit: (bid, basis, key, unique)."""
    hits = []

    def add(bids, basis, key, demote_registry=True):
        uniq = len(bids) == 1
        for bid in bids:
            b = basis
            if demote_registry and bid in ix.suspect and basis in V.STRONG_BASES:
                b = V.P_EXISTING_MAPPING          # suspect: registry mapping is support only
            hits.append((bid, b, key, uniq))

    for n in rec.get("numbers") or []:
        if n in ix.number:
            add(ix.number[n], V.P_TELEPHONE_MAPPING, n)
    for i in rec.get("idents") or []:
        if i in ix.ident:
            add(ix.ident[i], V.P_ASSET_IDENTIFIER, mask(i))

    def alias_hits(value, basis):
        k = nalias(value)
        if not k or k not in ix.alias:
            return
        classified = []
        for bid, intrinsic in ix.alias[k]:
            if k in ix.generic:
                b = V.P_GENERIC_ALIAS
            elif bid in ix.suspect and not intrinsic:
                b = V.P_EXISTING_MAPPING          # a suspect building's own aliases
            else:
                b = basis
            classified.append((bid, b))
        # uniqueness is judged per evidence class: a demoted (supporting) alias
        # never makes a building-specific alias ambiguous
        per_basis = defaultdict(set)
        for bid, b in classified:
            per_basis[b].add(bid)
        for bid, b in classified:
            hits.append((bid, b, k, len(per_basis[b]) == 1))

    for f in rec.get("facility") or []:
        alias_hits(f, V.P_FACILITY)
    for a in rec.get("account") or []:
        alias_hits(a, V.P_ACCOUNT_ALIAS)
    for p in rec.get("parent") or []:
        k = nalias(p)
        for bid, _intr in ix.alias.get(k, ()):
            hits.append((bid, V.P_GENERIC_ALIAS, k, False))
    for f in list(rec.get("facility") or []) + list(rec.get("account") or []):
        st = store_number(f)
        if st and st.upper() in ix.store:
            add(ix.store[st.upper()], V.P_STORE_NUMBER, st, demote_registry=False)
    if rec.get("address"):
        a = rec["address"]
        if a in ix.addr:
            add(ix.addr[a], V.P_ADDRESS, a, demote_registry=False)
    for bid in rec.get("support_bids") or ():
        hits.append((bid, V.P_EXISTING_MAPPING, "site-link", True))
    return hits


def place(ix: _Index, rec: dict, operator_bid=None) -> dict:
    """-> {building_id, confidence, basis, hits, candidates, legacy, note}."""
    hits = _hits(ix, rec)
    legacy = sorted({h[0] for h in hits if h[1] in V.SUPPORT_BASES})
    res = {"hits": hits, "legacy": legacy, "candidates": [], "note": None}
    if operator_bid is not None:
        return dict(res, building_id=operator_bid, confidence=V.CONFIRMED, basis=V.P_OPERATOR)

    usable = [h for h in hits if h[3]]
    strong = {h[0] for h in usable if h[1] in V.STRONG_BASES}
    loc = [h for h in usable if h[1] in V.LOCATION_BASES]
    ambiguous_loc = [h for h in hits if not h[3] and h[1] in V.LOCATION_BASES]
    best_loc, loc_bids = None, set()
    if loc:
        best_loc = min(V.PLACEMENT_PRIORITY[h[1]] for h in loc)
        loc_bids = {h[0] for h in loc if V.PLACEMENT_PRIORITY[h[1]] == best_loc}
    all_loc = {h[0] for h in loc}
    res["candidates"] = sorted(all_loc | {h[0] for h in ambiguous_loc})

    def out(bid, conf, basis, note=None):
        return dict(res, building_id=bid, confidence=conf, basis=basis, note=note)

    if len(strong) > 1:
        return out(None, V.UNRESOLVED, "CONFLICT", "identifier/number mapped to several buildings")
    if strong:
        b = next(iter(strong))
        basis = min((h[1] for h in usable if h[0] == b and h[1] in V.STRONG_BASES),
                    key=V.PLACEMENT_PRIORITY.get)
        if loc_bids and b not in loc_bids:
            return out(None, V.UNRESOLVED, "CONFLICT",
                       "mapping says one building, the source record's own location another")
        if not loc_bids and b in ix.suspect:
            return out(b, V.PROBABLE, basis, "suspect building: no location evidence")
        return out(b, V.CONFIRMED, basis)
    if len(loc_bids) > 1:
        return out(None, V.UNRESOLVED, "AMBIGUOUS", "location evidence names several buildings")
    if loc_bids:
        b = next(iter(loc_bids))
        basis = next(k for k, p in V.PLACEMENT_PRIORITY.items() if p == best_loc)
        if all_loc - {b}:
            return out(b, V.PROBABLE, basis, "weaker location evidence disagrees")
        if basis == V.P_ACCOUNT_ALIAS and b in ix.suspect:
            return out(b, V.PROBABLE, basis, "suspect building: account alias only")
        return out(b, V.CONFIRMED, basis)
    if ambiguous_loc:
        return out(None, V.UNRESOLVED, "AMBIGUOUS", "location key shared by several buildings")
    site_support = {h[0] for h in usable if h[1] == V.P_EXISTING_MAPPING}
    if len(site_support) == 1:
        b = next(iter(site_support))
        if b in ix.suspect:
            return out(None, V.UNRESOLVED, "LEGACY_ONLY",
                       "only a historical mapping to a suspect building")
        return out(b, V.PROBABLE, V.P_EXISTING_MAPPING, "historical mapping only")
    return out(None, V.UNRESOLVED, "UNMATCHED",
               "no building-specific evidence" if hits else "no key matched")


# ──────────────────────────────────────────────────────────── records ──

def _is_napco_device(d: dict) -> bool:
    """NAPCO / StarLink communicator hardware.  A populated ``starlink_id`` only
    counts when it has the shape of a radio number - a serial, IMEI, ICCID or
    telephone number typed into that column is not radio evidence."""
    t = words("%s %s %s" % (d.get("manufacturer"), d.get("model"), d.get("identifier_type")))
    return (" napco" in t or " starlink" in t or " slelte" in t or " sle " in t
            or bool(radio_id(d.get("starlink_id"))))


def _rejected(raw, radio):
    """The normalised value of a radio-typed field that was refused as a radio
    identity (for the RADIO_ID_REJECTED finding), else None."""
    return (nid(raw) or None) if raw and not radio else None


def _is_facp_device(d: dict, units: list[dict]) -> bool:
    t = words("%s %s" % (d.get("device_type"), d.get("model")))
    if any(w in t for w in (" fire", " facp ", " alarm control", " fire alarm")):
        return True
    return any(classify_label("%s %s" % (u.get("unit_type"), u.get("unit_name")))[0] == V.FACP
               for u in units)


def _records(snap: dict, ix: _Index) -> list[dict]:
    sites = {s["site_id"]: s for s in snap.get("sites") or []}
    lines_by_dev, units_by_dev = defaultdict(list), defaultdict(list)
    for ln in snap.get("lines") or []:
        if ln.get("device_id"):
            lines_by_dev[ln["device_id"]].append(ln)
    for u in snap.get("units") or []:
        if u.get("device_id"):
            units_by_dev[u["device_id"]].append(u)

    recs = []
    for z in snap.get("zoho_rows") or []:
        # A Subscription_Type that is a device SKU / plan ("SLELTE - Fire (Dual
        # Line)", often mass-updated) says nothing about the service: ignored.
        sub = z.get("subscription_type")
        label = " ".join(x for x in (z.get("connection_type"),
                                     None if is_sku_label(sub) else sub) if x)
        cat, strength = classify_label(label)
        radio = radio_id(z.get("starlink"))
        idents = [i for i in (nid(z.get("starlink")), nid(z.get("sim")), nid(z.get("imei")),
                              nid(z.get("serial"))) if i]
        recs.append({
            "rid": "zoho:%s" % z.get("zoho_id"), "source": V.SRC_ZOHO,
            "numbers": [n for n in [n10(z.get("msisdn"))] if n], "idents": idents,
            "napco": radio, "radio_rejected": _rejected(z.get("starlink"), radio),
            # a telephone line (valid MSISDN, no radio) - e.g. a dialer line
            # labelled "Alarm Panel" - is FACP equipment, never an FACP service
            "is_line": bool(n10(z.get("msisdn"))) and not radio,
            "iccid": nid(z.get("sim")) or None, "imei": nid(z.get("imei")) or None,
            "facility": [z.get("facility")] if z.get("facility") else [],
            "account": [z.get("account")] if z.get("account") else [],
            "parent": [z.get("parent")] if z.get("parent") else [],
            "address": None, "support_bids": set(),
            "label": label, "cat": cat, "strength": strength,
            "lifecycle": source_lifecycle(z.get("activation")),
            "status": z.get("activation"), "observed_at": z.get("modified"),
            "location_text": z.get("facility") or z.get("account") or z.get("parent"),
        })
    for d in snap.get("devices") or []:
        dl = lines_by_dev.get(d["device_id"], [])
        nums = sorted({n10(ln.get("did")) for ln in dl if n10(ln.get("did"))})
        if not nums and n10(d.get("msisdn")):
            nums = [n10(d.get("msisdn"))]
        site = sites.get(d.get("site_id")) or {}
        units = units_by_dev.get(d["device_id"], [])
        idents = [i for i in (nid(d.get("starlink_id")), nid(d.get("iccid")), nid(d.get("imei")),
                              nid(d.get("serial"))) if i]
        recs.append({
            "rid": "device:%s" % d["device_id"], "source": V.SRC_TRUE911, "device": d,
            "numbers": nums, "idents": idents,
            "napco": radio_id(d.get("starlink_id")) if _is_napco_device(d) else None,
            "radio_rejected": _rejected(d.get("starlink_id"), radio_id(d.get("starlink_id"))),
            "iccid": nid(d.get("iccid")) or None, "imei": nid(d.get("imei")) or None,
            "facility": [site.get("site_name")] if site.get("site_name") else [],
            "account": [], "parent": [],
            "address": naddr(site.get("street"), site.get("city"), site.get("state")) or None,
            "support_bids": set(ix.site_map.get(str(d.get("site_id")), ())),
            "lines": dl, "units": units,
            "is_facp": _is_facp_device(d, units), "is_napco": _is_napco_device(d),
            "lifecycle": source_lifecycle(d.get("status")),
            "status": d.get("status"), "observed_at": d.get("last_heartbeat"),
            "location_text": site.get("site_name") or d.get("site_id"),
        })
    for m in snap.get("mappings") or []:
        kind, val = m["kind"], m.get("value")
        if kind in ("phone", "genesis_msisdn") and n10(val):
            rec = {"numbers": [n10(val)], "idents": []}
        elif kind in ("napco_radio", "iccid", "imei") and nid(val):
            radio = radio_id(val) if kind == "napco_radio" else None
            rec = {"numbers": [], "idents": [nid(val)], "napco": radio,
                   "radio_rejected": _rejected(val, radio) if kind == "napco_radio" else None,
                   "iccid": nid(val) if kind == "iccid" else None,
                   "imei": nid(val) if kind == "imei" else None}
        else:
            continue
        recs.append(dict({"napco": None, "radio_rejected": None, "iccid": None, "imei": None},
                         **rec, **{
            "rid": "registry:%s#%s" % (kind, m.get("id")), "source": V.SRC_REGISTRY,
            "facility": [], "account": [], "parent": [], "address": None,
            "support_bids": set(), "lifecycle": None, "status": "mapped",
            "observed_at": None, "registry_kind": kind,
            "location_text": "registry mapping (%s)" % kind}))
    return recs


# ─────────────────────────────────────────────────────────── project ──

def project(snap: dict, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    dec = interpret_decisions(snap.get("decisions") or [])
    ix = _Index(snap, dec["suspect"])
    names = {bid: b.get("name") or "building %s" % bid for bid, b in ix.buildings.items()}
    sources = snap.get("sources") or {}
    degraded = any(s.get("status") != "ok" for s in sources.values() if s.get("required"))
    findings = []

    def finding(code, sev, bid, subject, detail):
        findings.append({"code": code, "severity": sev, "building_id": bid,
                         "building": names.get(bid), "subject": subject, "detail": detail})

    for name, s in sources.items():
        if s.get("required") and s.get("status") != "ok":
            finding("SOURCE_UNAVAILABLE", V.HIGH, None, name,
                    "%s: %s - confidence capped at PROBABLE; nothing stale is presented as current"
                    % (name, s.get("status")))

    for rad in dec["group_conflicts"]:
        finding("DECISION_CONFLICT", V.HIGH, None, "radio " + mask(rad),
                "named by more than one FACP_SERVICE decision - none of them applied")
    recs, excluded = [], []
    for r in _records(snap, ix):
        rd = dec["records"].get(r["rid"])
        if rd and rd["disposition"] in V.REC_EXCLUDING:
            # operator: not evidence of a service (kept for audit, never projected)
            excluded.append({"record": r["rid"], "disposition": rd["disposition"],
                             "duplicate_of": rd.get("duplicate_of"),
                             "location": rd.get("location"),
                             "location_text": r.get("location_text"),
                             "numbers": r["numbers"]})
            continue
        recs.append(r)
    for rid in sorted(set(dec["records"]) - {r["rid"] for r in recs}
                      - {e["record"] for e in excluded}):
        finding("DECISION_UNMATCHED", V.MEDIUM, None, rid,
                "operator SOURCE_RECORD decision names a record no source reports")
    # radios carried by a record the operator placed: every other record of the
    # same radio follows it (one radio cannot be at two buildings)
    rec_radio = {}
    for r in recs:
        rd = dec["records"].get(r["rid"])
        if rd and rd["disposition"] == V.REC_BUILDING and r.get("napco"):
            rec_radio.setdefault(_asset_key(V.NAPCO_RADIO, r["napco"]), rd["building_id"])
    for r in recs:
        # operator placement, most specific first: the record itself, one of
        # its numbers, or its operator-placed radio (a record follows the
        # equipment the operator placed)
        rd = dec["records"].get(r["rid"])
        op_bid = rd["building_id"] if rd and rd["disposition"] == V.REC_BUILDING else None
        if op_bid is None:
            op_bid = next((dec["place"][n] for n in r["numbers"] if n in dec["place"]), None)
        if op_bid is None and r.get("napco"):
            k = _asset_key(V.NAPCO_RADIO, r["napco"])
            op_bid = dec["place_asset"].get(k, rec_radio.get(k))
        r["placement"] = place(ix, r, op_bid)
        if r.get("radio_rejected"):
            finding("RADIO_ID_REJECTED", V.INFO, r["placement"]["building_id"],
                    "%s %s" % (r["rid"], mask(r["radio_rejected"])),
                    "value in a radio field has the shape of a serial / IMEI / ICCID / "
                    "telephone number - not used as a radio identity")

    # NAPCO evidence = the tenant's latest imported NAPCO radiolist snapshot
    # (D-024).  None = no snapshot loaded: radio ids are then unchecked, never
    # "NAPCO-backed".  Absence from a loaded snapshot caps confidence only; it
    # never changes lifecycle (it is not evidence of decommissioning).
    napco = snap.get("napco_radios")
    napco = None if napco is None else {radio_id(x) for x in napco if radio_id(x)}
    if napco is None:
        finding("NAPCO_EVIDENCE_NOT_LOADED", V.INFO, None, "napco_snapshot",
                "no NAPCO radiolist snapshot loaded - FACP radio ids are not checked "
                "against NAPCO and none is NAPCO-backed")

    # ── assets ─────────────────────────────────────────────────────
    assets = {}

    def asset(atype, value, rec):
        k = _asset_key(atype, value)
        a = assets.setdefault(k, {"key": k, "asset_type": atype, "normalized_value": value,
                                  "display_value": _display(atype, value), "records": [],
                                  "carrier": None})
        a["records"].append(rec)
        return k

    for r in recs:
        r["asset_keys"] = []
        for n in r["numbers"]:
            r["asset_keys"].append(asset(V.TELEPHONE_NUMBER, n, r))
        for atype, field in ((V.NAPCO_RADIO, "napco"), (V.SIM_ICCID, "iccid"),
                             (V.DEVICE_IMEI, "imei")):
            if r.get(field):
                r["asset_keys"].append(asset(atype, r[field], r))
        if r["source"] == V.SRC_TRUE911:
            carrier = (r["device"].get("carrier") or "").strip() or None
            for k in r["asset_keys"]:
                assets[k]["carrier"] = assets[k]["carrier"] or carrier
    for g in dec["facp_groups"]:
        for rad in g["radios"]:
            key = _asset_key(V.NAPCO_RADIO, rad)
            if key not in assets:
                finding("OPERATOR_ASSET_WITHOUT_SOURCE", V.INFO, g["building_id"], mask(rad),
                        "operator FACP_SERVICE '%s' names a radio no source reports" % g["ref"])
                assets[key] = {"key": key, "asset_type": V.NAPCO_RADIO, "normalized_value": rad,
                               "display_value": _display(V.NAPCO_RADIO, rad), "records": [],
                               "carrier": None}
    for key in dec["lifecycle"]:
        if key not in assets:
            atype, value = key.split(":", 1)
            finding("DECISION_UNMATCHED", V.MEDIUM, None, _display(atype, value),
                    "operator decision names an asset no source reports")
            assets[key] = {"key": key, "asset_type": atype, "normalized_value": value,
                           "display_value": _display(atype, value), "records": [],
                           "carrier": None}

    activity = _activity_index(snap.get("source_activity") or [])
    for a in assets.values():
        _place_asset(a, dec, finding, names)
        _asset_lifecycle(a, dec, activity, now, ix, finding)
        if a["building_id"] is None and a["asset_type"] == V.TELEPHONE_NUMBER:
            finding("UNPLACED_ASSET", V.MEDIUM, None, a["display_value"],
                    "; ".join(sorted({r["placement"]["note"] or r["placement"]["basis"]
                                      for r in a["records"]})) or "no source placement")

    # ── telephone classification ───────────────────────────────────
    for a in assets.values():
        if a["asset_type"] == V.TELEPHONE_NUMBER:
            _classify_number(a, dec, finding)
    _apply_pools(assets, dec, finding)

    # ── FACP services (per building, joined across sources) ────────
    services = []
    by_bldg = defaultdict(list)
    for r in recs:
        if r["placement"]["building_id"] is not None:
            by_bldg[r["placement"]["building_id"]].append(r)
    fused = [[i for i in g if i] for g in snap.get("fused_groups") or []]
    for bid in sorted(ix.buildings):
        services.extend(_facp_services(
            bid, by_bldg.get(bid, []), fused, assets, finding, napco,
            groups=[g for g in dec["facp_groups"] if g["building_id"] == bid]))

    # ── telephone services ─────────────────────────────────────────
    for a in sorted(assets.values(), key=lambda x: x["key"]):
        if a["asset_type"] != V.TELEPHONE_NUMBER or a["building_id"] is None:
            continue
        cls = a["classification"]
        if cls not in (V.ELEVATOR, V.EMERGENCY_PHONE, V.UNCLASSIFIED):
            continue
        conf = V.UNRESOLVED if cls == V.UNCLASSIFIED else V.weakest(
            a["classification_confidence"], a["placement_confidence"])
        services.append({
            "building_id": a["building_id"],
            "service_key": "%s:tel:%s" % (_PREFIX[cls], a["normalized_value"]),
            "service_type": cls,
            "display_name": a.get("classification_label") or _DISPLAY[cls],
            "confidence": conf, "lifecycle": a["lifecycle"],
            "lifecycle_reason": a["lifecycle_reason"],
            "deployment": a["deployment"], "deployment_basis": a["deployment_basis"],
            "source_status": a["source_status"],
            "assets": [(a["key"], V.REL_CARRIER_LINE)],
            "evidence": a["classification_evidence"],
        })

    # ── approval, degradation, eligibility, connections ────────────
    connections = []
    for s in services:
        s["approval"] = dec["approval"].get((s["building_id"], s["service_key"]),
                                            V.APPROVAL_NONE)
        if degraded and s["confidence"] == V.CONFIRMED:
            s["confidence"] = V.PROBABLE
            s["degraded"] = True
        s["counts"] = (s["service_type"] in V.LIFE_SAFETY_TYPES
                       and s["approval"] != V.REJECTED
                       and (s["confidence"] == V.CONFIRMED or s["approval"] == V.APPROVED)
                       and s["lifecycle"] == V.CURRENT
                       and s.get("deployment") == V.DEPLOYED)
        s["probable"] = (s["service_type"] in V.LIFE_SAFETY_TYPES and not s["counts"]
                         and s["approval"] != V.REJECTED and s["confidence"] == V.PROBABLE
                         and s["lifecycle"] not in V.NOT_CURRENT)
        if not s["counts"]:
            continue
        for ordinal in range(1, V.REQUIRED_CONNECTIONS[s["service_type"]] + 1):
            links = []
            for akey, rel in s["assets"]:
                if rel == V.REL_CARRIER_LINE and ordinal == 1:
                    links.append((akey, rel))
                elif rel == V.REL_SERVICE_EQUIPMENT:
                    links.append((akey, rel))
            if s["service_type"] == V.FACP:
                prov = V.NOT_EVALUATED
            else:
                prov = V.ASSET_LINKED if any(r == V.REL_CARRIER_LINE for _, r in links) \
                    else V.NO_ASSET_LINKED
            connections.append({
                "building_id": s["building_id"], "service_key": s["service_key"],
                "ordinal": ordinal, "connection_type": V.CONNECTION_TYPE[s["service_type"]],
                "requirement": V.REQUIRED, "provisioning": prov,
                "confidence": V.CONFIRMED if s["confidence"] == V.CONFIRMED else s["confidence"],
                "links": links})
    for s in services:
        if s["service_type"] in V.LIFE_SAFETY_TYPES and s["lifecycle"] == V.CURRENT \
                and s["confidence"] == V.CONFIRMED and s.get("deployment") != V.DEPLOYED:
            finding("DEPLOYMENT_NOT_ESTABLISHED", V.INFO, s["building_id"], s["service_key"],
                    "CURRENT but not deterministically deployed at this building - not counted")
        if s["service_type"] in V.LIFE_SAFETY_TYPES and s["lifecycle"] == V.UNKNOWN \
                and s["confidence"] == V.CONFIRMED:
            finding("LIFECYCLE_UNKNOWN", V.INFO, s["building_id"], s["service_key"],
                    "confirmed service whose current deployment no independent evidence "
                    "establishes (an administrative status alone is not deployment) - not counted")

    result = {
        "generated_at": now, "tenant_id": snap.get("tenant_id"), "sources": sources,
        "degraded": degraded, "assets": assets, "services": services,
        "connections": connections, "findings": findings, "records": recs,
        "lifecycle_events": dec["events"], "suspect_building_ids": sorted(dec["suspect"]),
        "excluded_records": excluded, "operator_pools": dec["pools"],
        "building_names": names,
    }
    result["building_summaries"] = _building_summaries(result, ix)
    result["portfolio"] = _portfolio(result)
    result["suspect_reports"] = [_suspect_report(result, bid) for bid in sorted(dec["suspect"])]
    return result


# ─────────────────────────────────────────────────────────── helpers ──

def _place_asset(a, dec, finding, names):
    op = (dec["place"].get(a["normalized_value"]) if a["asset_type"] == V.TELEPHONE_NUMBER
          else dec["place_asset"].get(a["key"]))
    if op is None:
        # a record the operator placed carries its other identifiers with it
        op_bids = {r["placement"]["building_id"] for r in a["records"]
                   if r["placement"]["basis"] == V.P_OPERATOR}
        op = next(iter(op_bids)) if len(op_bids) == 1 else None
    if op is not None:
        a.update(building_id=op, placement_confidence=V.CONFIRMED, placement_basis=V.P_OPERATOR)
        return
    placements = [r["placement"] for r in a["records"]]
    conf = {p["building_id"] for p in placements if p["confidence"] == V.CONFIRMED}
    prob = {p["building_id"] for p in placements if p["confidence"] == V.PROBABLE}
    if len(conf) == 1:
        b = next(iter(conf))
        basis = min((p["basis"] for p in placements if p["building_id"] == b
                     and p["confidence"] == V.CONFIRMED), key=lambda x: V.PLACEMENT_PRIORITY.get(x, 9))
        a.update(building_id=b, placement_confidence=V.CONFIRMED, placement_basis=basis)
        if prob - conf:
            finding("ASSET_PLACEMENT_DISAGREEMENT", V.MEDIUM, b, a["display_value"],
                    "weaker evidence also points to %s" % ", ".join(
                        str(names.get(x)) for x in sorted(prob - conf)))
    elif len(conf) > 1:
        a.update(building_id=None, placement_confidence=V.UNRESOLVED, placement_basis="CONFLICT")
        finding("ASSET_PLACEMENT_CONFLICT", V.HIGH, None, a["display_value"],
                "sources confirm different buildings: %s" % ", ".join(
                    str(names.get(x)) for x in sorted(conf)))
    elif len(prob) == 1:
        b = next(iter(prob))
        basis = next(p["basis"] for p in placements if p["building_id"] == b)
        a.update(building_id=b, placement_confidence=V.PROBABLE, placement_basis=basis)
    else:
        a.update(building_id=None, placement_confidence=V.UNRESOLVED,
                 placement_basis="AMBIGUOUS" if len(prob) > 1 else "UNMATCHED")


def _aware(t):
    if isinstance(t, str):
        try:
            t = datetime.fromisoformat(t.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(t, datetime):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _recent(t, now) -> bool:
    t = _aware(t)
    return bool(t) and timedelta(0) - timedelta(days=1) <= now - t \
        <= timedelta(days=V.DEPLOYMENT_ACTIVITY_DAYS)


_ACTIVITY_FIELD = {V.TELEPHONE_NUMBER: "msisdn", V.NAPCO_RADIO: "napco_radio",
                   V.SIM_ICCID: "iccid", V.DEVICE_IMEI: "imei"}


def _activity_index(rows) -> dict:
    """(field, normalised identifier) -> source activity rows."""
    ix = defaultdict(list)
    for row in rows:
        for atype, field in _ACTIVITY_FIELD.items():
            v = row.get(field)
            v = (n10(v) if atype == V.TELEPHONE_NUMBER else
                 radio_id(v) if atype == V.NAPCO_RADIO else nid(v)) if v else None
            if v:
                ix[(atype, v)].append(row)
    return ix


def _placed_deterministically(a) -> bool:
    """Placement independent of the record's own CRM location fields."""
    return (a.get("building_id") is not None and a.get("placement_confidence") == V.CONFIRMED
            and a.get("placement_basis") in V.DEPLOYMENT_PLACEMENT_BASES)


def _liveness(a, activity, now, ix, finding):
    """Recent evidence that the equipment is ALIVE (not where it is), or None.
    -> (reason, source, observed_at)."""
    for r in a["records"]:
        if r["source"] == V.SRC_TRUE911 and _recent(r["device"].get("last_heartbeat"), now):
            return V.REASON_DEPLOYMENT_TELEMETRY, V.SRC_TRUE911, r["device"]["last_heartbeat"]
    bstore = (ix.buildings.get(a.get("building_id")) or {}).get("store_number")
    for row in activity.get((a["asset_type"], a["normalized_value"]), ()):
        if row.get("source") not in V.DEPLOYMENT_ACTIVITY_SOURCES:
            continue                           # inventory status only (e.g. Verizon)
        if row.get("lifecycle") in V.NOT_CURRENT or not _recent(row.get("activity_at"), now):
            continue
        hint = store_number(row.get("location_hint"))
        if bstore and hint and str(hint) != str(bstore).lstrip("0"):
            # the source names another store: possibly moved - never carried to
            # THIS building
            finding("DEPLOYMENT_LOCATION_CONFLICT", V.MEDIUM, a.get("building_id"),
                    a["display_value"], "%s reports recent activity under store %s"
                    % (row["source"], hint))
            continue
        return V.REASON_DEPLOYMENT_ACTIVITY, row["source"], row.get("activity_at")
    return None


def _asset_lifecycle(a, dec, activity=None, now=None, ix=None, finding=None):
    a.update(effective_from=None, effective_to=None, lifecycle_event_key=None,
             deployment=V.DEPLOYMENT_NOT_ESTABLISHED, deployment_basis=None,
             deployment_observed_at=None, source_status=None,
             liveness_source=None, liveness_at=None)
    placed = _placed_deterministically(a)
    op = dec["lifecycle"].get(a["key"])
    if op:
        # governed operator truth: never ages out with source exports
        a.update(lifecycle=op["lifecycle"], lifecycle_reason=op.get("reason"),
                 lifecycle_source=V.SRC_OPERATOR, effective_from=op.get("effective_from"),
                 effective_to=op.get("effective_to"), lifecycle_event_key=op.get("event_key"))
        if op["lifecycle"] == V.CURRENT:
            if placed:
                a.update(deployment=V.DEPLOYED, deployment_basis=V.REASON_OPERATOR)
            elif finding:
                finding("DEPLOYMENT_PLACEMENT_UNVERIFIED", V.MEDIUM, a.get("building_id"),
                        a["display_value"], "operator says CURRENT but the building "
                        "placement is not deterministic - not DEPLOYED")
        if op.get("carrier"):
            a["carrier"] = op["carrier"]
        return
    admin = None                               # (lifecycle, reason, source) - status words
    for src in (V.SRC_ZOHO, V.SRC_TRUE911):
        states = [r["lifecycle"] for r in a["records"] if r["source"] == src and r["lifecycle"]]
        if not states:
            continue
        if any(s[0] == V.CURRENT for s in states):
            lc = (V.CURRENT, V.REASON_SOURCE_ACTIVE)
        elif any(s[0] == V.SUSPENDED for s in states):
            lc = (V.SUSPENDED, V.REASON_SOURCE_SUSPENDED)
        else:
            lc = states[0]
        if src == V.SRC_TRUE911:
            lc = (lc[0], V.REASON_TRUE911_STATUS)
        admin = (lc[0], lc[1], src)
        a["source_status"] = "%s:%s" % (src, lc[0])
        break
    live = _liveness(a, activity or {}, now, ix, finding) if ix is not None else None
    if live:
        a.update(liveness_source=live[1], liveness_at=live[2])
        if admin and admin[0] in V.NOT_CURRENT and finding:
            finding("LIFECYCLE_CONFLICT", V.MEDIUM, a.get("building_id"), a["display_value"],
                    "%s says %s but %s shows recent activity" % (admin[2], admin[0], live[1]))
    if live and placed:
        a.update(lifecycle=V.CURRENT, lifecycle_reason=live[0], lifecycle_source=live[1],
                 deployment=V.DEPLOYED, deployment_basis=live[0],
                 deployment_observed_at=live[2])
    elif admin and admin[0] in V.NOT_CURRENT:
        a.update(lifecycle=admin[0], lifecycle_reason=admin[1], lifecycle_source=admin[2])
    elif live:
        # alive somewhere - but nothing independent says it is at THIS building
        a.update(lifecycle=V.UNKNOWN, lifecycle_reason=V.REASON_PLACEMENT_UNVERIFIED,
                 lifecycle_source=live[1])
        if finding and a.get("building_id") is not None:
            finding("ACTIVE_PLACEMENT_UNVERIFIED", V.INFO, a["building_id"], a["display_value"],
                    "%s shows recent activity, but the building placement (%s) is not "
                    "deterministic - not DEPLOYED" % (live[1], a.get("placement_basis")))
    elif admin:
        a.update(lifecycle=V.UNKNOWN, lifecycle_reason=V.REASON_ADMIN_STATUS_ONLY,
                 lifecycle_source=admin[2])
    else:
        a.update(lifecycle=V.UNKNOWN, lifecycle_reason=None, lifecycle_source=None)


def _apply_pools(assets, dec, finding):
    """SERVICE_POOL: the operator knows a SET of lines is e.g. emergency phone /
    fax, not which line is which.  A member is never given a per-line class by
    the pool; a source label on it can be at most PROBABLE (the pool says the
    set is mixed); a class outside the pool's types is a conflict."""
    for pool in dec["pools"]:
        open_lines = 0
        for n in pool["numbers"]:
            a = assets.get(_asset_key(V.TELEPHONE_NUMBER, n))
            if a is None:
                finding("DECISION_UNMATCHED", V.MEDIUM, pool["building_id"], n,
                        "SERVICE_POOL '%s' names a number no source reports" % pool["ref"])
                continue
            a["pool"] = pool["ref"]
            note = "operator pool '%s' (%s): per-line purpose not assigned" % (
                pool["ref"], "/".join(pool["service_types"]))
            a["classification_evidence"] = list(a.get("classification_evidence") or []) + [note]
            if n in dec["classify"]:
                continue                      # an explicit per-number decision holds
            cls = a.get("classification")
            if cls in pool["service_types"]:
                a["classification_confidence"] = V.weakest(a["classification_confidence"],
                                                           V.PROBABLE)
            elif cls not in (V.UNCLASSIFIED, None):
                a.update(classification=V.UNCLASSIFIED, classification_confidence=V.UNRESOLVED)
                finding("POOL_CLASSIFICATION_CONFLICT", V.MEDIUM, pool["building_id"], n,
                        "source class %s is outside operator pool '%s'" % (cls, pool["ref"]))
            if a.get("classification") in (V.UNCLASSIFIED, None) or \
                    a.get("classification_confidence") != V.CONFIRMED:
                open_lines += 1
        finding("SERVICE_POOL_UNASSIGNED", V.INFO, pool["building_id"], pool["ref"],
                "%d of %d pooled line(s) without a per-line purpose (%s) - not counted as "
                "individual services" % (open_lines, len(pool["numbers"]),
                                         "/".join(pool["service_types"])))


def _classify_number(a, dec, finding):
    n = a["normalized_value"]
    ev = []                                    # (source, category, strength, active, detail)
    for r in a["records"]:
        if r["source"] == V.SRC_ZOHO:
            active = not (r["lifecycle"] and r["lifecycle"][0] in V.NOT_CURRENT)
            ev.append((V.SRC_ZOHO, r["cat"], r["strength"], active,
                       "zoho %s label='%s' status=%s" % (r["rid"][5:], r["label"], r["status"])))
        elif r["source"] == V.SRC_TRUE911:
            d = r["device"]
            if r["is_facp"]:
                ev.append((V.SRC_TRUE911, V.FACP, "explicit", True,
                           "device %s is FACP equipment" % d["device_id"]))
            elif len(r["numbers"]) == 1:
                from app.services.customer import service_inference as si
                stype, sconf, _src = si.classify({
                    "device_id": d["device_id"], "model": d.get("model"),
                    "device_type": d.get("device_type"),
                    "manufacturer": d.get("manufacturer"), "notes": d.get("notes")})
                if d.get("override_service_type"):
                    stype, sconf = d["override_service_type"], "override"
                cat = _INFERRED.get(stype)
                if cat:
                    ev.append((V.SRC_TRUE911, cat, "inferred", True,
                               "device %s inferred %s (%s)" % (d["device_id"], stype, sconf)))
            else:
                finding("MULTI_NUMBER_DEVICE", V.INFO, a.get("building_id"), n,
                        "device %s carries %d numbers - equipment type not applied per number"
                        % (d["device_id"], len(r["numbers"])))
            for ln in r.get("lines") or []:
                if n10(ln.get("did")) == n:
                    cat, st = classify_label("%s %s %s" % (ln.get("line_type"),
                                                           ln.get("description"), ln.get("notes")))
                    if cat:
                        ev.append((V.SRC_TRUE911, cat, st, True,
                                   "line %s type=%s" % (ln.get("line_id"), ln.get("line_type"))))
            for u in r.get("units") or []:
                line_nums = {n10(ln.get("did")) for ln in r.get("lines") or []
                             if ln.get("line_id") == u.get("line_id")}
                if (u.get("line_id") and n in line_nums) or (not u.get("line_id")
                                                             and len(r["numbers"]) == 1):
                    cat, st = classify_label("%s %s" % (u.get("unit_type"), u.get("unit_name")))
                    if cat:
                        ev.append((V.SRC_TRUE911, cat, st, True,
                                   "service unit %s type=%s" % (u.get("unit_id"), u.get("unit_type"))))
    a["classification_evidence"] = [e[4] for e in ev]
    a["classification_label"] = None
    if n in dec["classify"]:
        st, label = dec["classify"][n]
        a.update(classification=st, classification_confidence=V.CONFIRMED,
                 classification_label=label)
        a["classification_evidence"].append("operator decision SERVICE_CLASSIFICATION")
        return
    expl = {e[1] for e in ev if e[1] and e[2] == "explicit" and e[3]}
    infer = {e[1] for e in ev if e[1] and e[2] == "inferred"}
    if expl == {V.FACP}:
        cls, conf = V.FACP_ASSET, V.CONFIRMED
    elif len(expl - {V.FACP}) > 1:
        cls, conf = V.UNCLASSIFIED, V.UNRESOLVED
        finding("CLASSIFICATION_CONFLICT", V.MEDIUM, a.get("building_id"), n,
                "explicit labels disagree: %s" % "/".join(sorted(expl)))
    elif expl - {V.FACP}:
        cls, conf = next(iter(expl - {V.FACP})), V.CONFIRMED
    elif len(infer) == 1 and next(iter(infer)) in (V.ELEVATOR, V.EMERGENCY_PHONE):
        cls, conf = next(iter(infer)), V.PROBABLE
    elif infer == {V.FACP}:
        cls, conf = V.FACP_ASSET, V.PROBABLE
    else:
        cls, conf = V.UNCLASSIFIED, V.UNRESOLVED
    a.update(classification=cls, classification_confidence=conf)
    if cls == V.UNCLASSIFIED and a.get("building_id") is not None \
            and a.get("lifecycle") not in V.NOT_CURRENT:
        finding("UNCLASSIFIED_NUMBER", V.INFO, a["building_id"], n,
                "no source labels this line's service")


def _facp_services(bid, recs, fused, assets, finding, napco=None, groups=()) -> list[dict]:
    """FACP services for one building.  A service is keyed by its radio
    identity (``FACP:radio:<id>``) whatever source reported it; which sources
    did is PROVENANCE (``provenance.sources``), and only a radio present in a
    loaded NAPCO snapshot is ``napco_backed``.  Joins are exact normalised
    identifiers only - never fuzzy, never dropped-digit."""
    uf = _UF()
    napcos = {}                                # radio id -> placement confidence
    radio_src = defaultdict(set)               # radio id -> sources claiming it
    members = {}                               # record key -> record
    kinds = defaultdict(set)
    # a radio the operator placed at ANOTHER building never forms a service here
    elsewhere = {a["normalized_value"] for a in assets.values()
                 if a["asset_type"] == V.NAPCO_RADIO and a.get("placement_basis") == V.P_OPERATOR
                 and a.get("building_id") != bid}
    for r in recs:
        if r.get("napco") and r["napco"] not in elsewhere:
            napcos[r["napco"]] = max(napcos.get(r["napco"], V.UNRESOLVED),
                                     r["placement"]["confidence"],
                                     key=lambda c: V.CONFIDENCE_RANK[c])
            radio_src[r["napco"]].add(r["source"])
            uf.find("I:" + r["napco"])
        is_facp_rec = (r["source"] == V.SRC_TRUE911 and r["is_facp"]) or (
            r["source"] == V.SRC_ZOHO and r["cat"] == V.FACP and not r.get("is_line")
            and not (r["lifecycle"] and r["lifecycle"][0] in V.NOT_CURRENT))
        joinable = is_facp_rec or (r["source"] == V.SRC_TRUE911 and r["is_napco"])
        if not joinable:
            continue
        key = "R:" + r["rid"]
        if is_facp_rec:
            members[key] = r
        for i in r["idents"]:
            uf.union(key, "I:" + i)
            kinds[key].add("identifier")
        for n in r["numbers"]:
            uf.union(key, "I:" + n)
    for g in groups:                         # operator: these radios are ONE service
        for rad in g["radios"]:
            napcos[rad] = V.CONFIRMED
            radio_src[rad].add(V.SRC_OPERATOR)
            uf.union("I:" + g["radios"][0], "I:" + rad)
    known = set(uf.p)
    for grp in fused:
        nodes = ["I:" + (n10(i) or nid(i)) for i in grp]
        if any(x in known for x in nodes):
            for x in nodes[1:]:
                uf.union(nodes[0], x)
            for x in nodes:
                kinds[x].add("approved registry linkage")
    comps = defaultdict(lambda: {"nap": set(), "recs": [], "kinds": set()})
    for n in napcos:
        comps[uf.find("I:" + n)]["nap"].add(n)
    for k, r in members.items():
        comps[uf.find(k)]["recs"].append(r)
    for node, ks in kinds.items():
        if node in uf.p:
            comps[uf.find(node)]["kinds"] |= ks

    out = []
    flagged = set()

    def svc(key, conf, comp_recs, naps, evidence, operator=False):
        placement = [r["placement"]["confidence"] for r in comp_recs]
        placement += [napcos[n] for n in naps if n in napcos]
        conf = V.weakest(conf, *placement) if placement else conf
        evidence = list(evidence)
        claimed = set().union(*(radio_src.get(n, set()) for n in naps)) if naps else set()
        backed = bool(naps) and napco is not None and all(n in napco for n in naps)
        sources = claimed | {r["source"] for r in comp_recs}
        if backed:
            sources.add(V.SRC_NAPCO)
        if operator:
            sources.add(V.SRC_OPERATOR)
        if naps and not operator and not backed and not (claimed - {V.SRC_ZOHO}) \
                and conf == V.CONFIRMED:
            # a radio id only Zoho reports is Zoho evidence, not NAPCO evidence
            conf = V.PROBABLE
            evidence.append("radio id reported only by Zoho - not corroborated by NAPCO, "
                            "True911 or the registry")
            finding("FACP_RADIO_SINGLE_SOURCE", V.MEDIUM, bid,
                    "radio " + ",".join(mask(n) for n in sorted(naps)),
                    "FACP radio identity rests on Zoho alone - capped at PROBABLE")
        if naps and napco is not None and not backed:
            # operator truth is not capped by a source's silence; it is still reported
            if not operator:
                conf = V.weakest(conf, V.PROBABLE)
            absent = sorted(n for n in naps if n not in napco)
            evidence.append("radio %s absent from the NAPCO radiolist snapshot"
                            % ",".join(mask(n) for n in absent))
            for n in absent:
                if n not in flagged:
                    flagged.add(n)
                    finding("RADIO_NOT_IN_NAPCO", V.MEDIUM, bid, "radio " + mask(n),
                            "not among the tenant-attributed rows of the latest NAPCO "
                            "radiolist snapshot - capped at PROBABLE; lifecycle unchanged "
                            "(absence is not decommissioning)")
        prov = {"radio_ids": sorted(naps), "sources": sorted(sources),
                "napco_evidence": ("NOT_LOADED" if napco is None else
                                   "PRESENT" if backed else
                                   "ABSENT" if naps else "NO_RADIO"),
                "napco_backed": backed}
        linked = [(_asset_key(V.NAPCO_RADIO, n), V.REL_SERVICE_EQUIPMENT) for n in sorted(naps)]
        for r in comp_recs:
            for k in r["asset_keys"]:
                a = assets[k]
                if a["asset_type"] == V.TELEPHONE_NUMBER and a.get("classification") != V.FACP_ASSET:
                    continue
                if (k, V.REL_SERVICE_EQUIPMENT) not in linked:
                    linked.append((k, V.REL_SERVICE_EQUIPMENT))
        # lifecycle: an operator decision on the equipment, else deployment
        # evidence on any of it, else only a negative source status; a source's
        # "Activated" alone leaves UNKNOWN.
        equip = [assets[k] for k, _r in linked if k in assets]
        op = [a for a in equip if a.get("lifecycle_source") == V.SRC_OPERATOR]
        deployed = [a for a in equip if a.get("deployment") == V.DEPLOYED
                    and a.get("building_id") == bid]
        unplaced = [a for a in equip if a.get("lifecycle_reason") == V.REASON_PLACEMENT_UNVERIFIED]
        states = [r["lifecycle"][0] for r in comp_recs if r["lifecycle"]]
        dep, dep_basis = V.DEPLOYMENT_NOT_ESTABLISHED, None
        if op and all(a["lifecycle"] in V.NOT_CURRENT for a in op):
            lc, why = op[0]["lifecycle"], op[0]["lifecycle_reason"]
        elif deployed:
            lc, why = V.CURRENT, deployed[0]["lifecycle_reason"]
            dep, dep_basis = V.DEPLOYED, deployed[0]["deployment_basis"]
        elif op and any(a["lifecycle"] == V.CURRENT for a in op):
            lc, why = V.CURRENT, V.REASON_OPERATOR        # operator truth, placement unverified
        elif unplaced:
            lc, why = V.UNKNOWN, V.REASON_PLACEMENT_UNVERIFIED
        elif states and all(s in V.NOT_CURRENT for s in states):
            lc, why = states[0], V.REASON_SOURCE_DEACTIVATED
        else:
            lc = V.UNKNOWN
            why = V.REASON_ADMIN_STATUS_ONLY if V.CURRENT in states else None
        out.append({"building_id": bid, "service_key": key, "service_type": V.FACP,
                    "display_name": _DISPLAY[V.FACP], "confidence": conf, "lifecycle": lc,
                    "lifecycle_reason": why, "deployment": dep, "deployment_basis": dep_basis,
                    "source_status": ",".join(sorted({"%s:%s" % (r["source"], r["lifecycle"][0])
                                                      for r in comp_recs if r["lifecycle"]}))
                    or None,
                    "assets": linked, "evidence": evidence, "provenance": prov})

    for g in groups:
        c = comps.get(uf.find("I:" + g["radios"][0])) or {"nap": set(), "recs": [], "kinds": set()}
        svc("FACP:radio:%s" % "+".join(g["radios"]), V.CONFIRMED, c["recs"], set(g["radios"]),
            ["operator FACP_SERVICE '%s': one FACP served by %d communicator(s) %s"
             % (g["ref"], len(g["radios"]), ",".join(mask(x) for x in g["radios"]))],
            operator=True)
        extra = c["nap"] - set(g["radios"])
        if extra:
            finding("FACP_OPERATOR_GROUP_EXTRA", V.MEDIUM, bid, "radio " + ",".join(
                mask(x) for x in sorted(extra)), "joined to operator FACP '%s' by shared "
                "identifiers but not named by it - left unresolved" % g["ref"])
        c["nap"], c["recs"] = extra, []        # its records are now that service's evidence
    nap_only, rec_only = [], []
    for c in comps.values():
        if c["nap"] and c["recs"]:
            devs = [r for r in c["recs"] if r["source"] == V.SRC_TRUE911]
            if devs and len(c["nap"]) != len(devs):
                for n in sorted(c["nap"]):
                    svc("FACP:radio:%s" % n, V.UNRESOLVED, c["recs"], {n},
                        ["%d radio ids vs %d FACP devices joined" % (len(c["nap"]), len(devs))])
                finding("FACP_UNRESOLVED", V.MEDIUM, bid, "radio " + ",".join(
                    mask(n) for n in sorted(c["nap"])), "count mismatch in joined component")
                continue
            ev = ["radio %s joined to %s via %s" % (
                ",".join(mask(n) for n in sorted(c["nap"])),
                ",".join(r["rid"] for r in c["recs"]),
                ",".join(sorted(c["kinds"])) or "shared identifier")]
            for n in sorted(c["nap"]):
                svc("FACP:radio:%s" % n, V.CONFIRMED, c["recs"], {n}, ev)
        elif c["nap"]:
            nap_only.append(c)
        elif c["recs"]:
            rec_only.append(c)
    if len(nap_only) == 1 and len(rec_only) == 1:
        c, rc = nap_only[0], rec_only[0]
        for n in sorted(c["nap"]):
            svc("FACP:radio:%s" % n, V.CONFIRMED, rc["recs"], {n},
                ["unique one-to-one in building: radio %s <-> %s" % (
                    mask(n), ",".join(r["rid"] for r in rc["recs"]))])
    else:
        naps = sorted(n for c in nap_only for n in c["nap"])
        rcs = sorted(rec_only, key=lambda c: c["recs"][0]["rid"])
        pairs = min(len(naps), len(rcs))
        for i, n in enumerate(naps):
            if i < pairs:
                svc("FACP:radio:%s" % n, V.PROBABLE, rcs[i]["recs"], {n},
                    ["%d radio ids + %d FACP records - pairing ambiguous" % (len(naps), len(rcs))])
            else:
                svc("FACP:radio:%s" % n, V.UNRESOLVED, [], {n},
                    ["radio id without FACP evidence"])
        for c in rcs[pairs:]:
            r0 = c["recs"][0]
            svc("FACP:%s" % r0["rid"], V.PROBABLE if not naps else V.UNRESOLVED, c["recs"],
                set(), ["FACP record without a radio identity"])
        if naps and rcs:
            finding("FACP_PROBABLE", V.MEDIUM, bid, "%d radio / %d records" % (len(naps), len(rcs)),
                    "pairing is ambiguous - operator review")
        elif naps:
            finding("FACP_UNRESOLVED", V.MEDIUM, bid, "radio " + ",".join(mask(n) for n in naps),
                    "radio id(s) without FACP evidence")
        elif rcs:
            finding("FACP_PROBABLE", V.MEDIUM, bid, ",".join(c["recs"][0]["rid"] for c in rcs),
                    "FACP record(s) without a radio identity")
    return out


def _building_summaries(res, ix) -> list[dict]:
    out = []
    for bid in sorted(ix.buildings, key=lambda b: str(ix.buildings[b].get("name"))):
        svcs = [s for s in res["services"] if s["building_id"] == bid]
        conns = [c for c in res["connections"] if c["building_id"] == bid]
        assets = [a for a in res["assets"].values() if a["building_id"] == bid]
        confirmed = Counter(s["service_type"] for s in svcs if s["counts"])
        probable = [s for s in svcs if s["probable"]]
        out.append({
            "building_id": bid, "name": res["building_names"][bid],
            "suspect": bid in ix.suspect,
            "confirmed_services": dict(confirmed),
            "confirmed_service_total": sum(confirmed.values()),
            "probable_services": len(probable),
            "unresolved_services": sum(1 for s in svcs if s["service_type"] in V.LIFE_SAFETY_TYPES
                                       and s["confidence"] == V.UNRESOLVED),
            "unclassified_lines": sum(1 for s in svcs if s["service_type"] == V.UNCLASSIFIED
                                      and s["lifecycle"] not in V.NOT_CURRENT),
            "required_connections": len(conns),
            "probable_additional_connections": sum(
                V.REQUIRED_CONNECTIONS[s["service_type"]] for s in probable),
            "current_assets": dict(Counter(a["asset_type"] for a in assets
                                           if a["lifecycle"] == V.CURRENT)),
            "historical_assets": sum(1 for a in assets if a["lifecycle"] in V.NOT_CURRENT),
        })
    return out


def _portfolio(res) -> dict:
    bs = res["building_summaries"]
    confirmed = Counter()
    for b in bs:
        confirmed.update(b["confirmed_services"])
    unresolved = sum(b["unresolved_services"] for b in bs)
    unclassified = sum(b["unclassified_lines"] for b in bs)
    return {
        "buildings": len(bs),
        "confirmed_services": dict(confirmed),
        "confirmed_service_total": sum(confirmed.values()),
        "probable_services": sum(b["probable_services"] for b in bs),
        "unresolved_services": unresolved,
        "unclassified_lines": unclassified,
        "confirmed_required_connections": sum(b["required_connections"] for b in bs),
        "probable_additional_connections": sum(b["probable_additional_connections"] for b in bs),
        "unplaced_telephone_numbers": sum(
            1 for a in res["assets"].values()
            if a["asset_type"] == V.TELEPHONE_NUMBER and a["building_id"] is None),
        "historical_assets": sum(1 for a in res["assets"].values()
                                 if a["lifecycle"] in V.NOT_CURRENT),
        "precise_total_available": unresolved == 0 and unclassified == 0 and not res["degraded"],
        "findings": dict(Counter(f["code"] for f in res["findings"])),
        "degraded": res["degraded"],
    }


def _suspect_report(res, bid) -> dict:
    names = res["building_names"]
    confirmed_assets = sorted(a["display_value"] for a in res["assets"].values()
                              if a["building_id"] == bid and a["placement_confidence"] == V.CONFIRMED)
    confirmed_services = sorted(s["service_key"] for s in res["services"]
                                if s["building_id"] == bid and s["counts"])
    imported, unmatched = [], []
    for r in res["records"]:
        p = r["placement"]
        if bid not in p["legacy"] and p["building_id"] != bid:
            continue
        if p["building_id"] == bid and p["confidence"] == V.CONFIRMED:
            continue
        entry = {
            "record": r["rid"], "source": r["source"],
            "location_text": r.get("location_text"),
            "numbers": list(r["numbers"]), "identifiers": [mask(i) for i in r["idents"]],
            "placed_to": names.get(p["building_id"]), "placement_confidence": p["confidence"],
            "basis": p["basis"], "note": p["note"],
            "source_building_candidates": [names.get(c) for c in p["candidates"] if c != bid],
            "evidence": sorted({"%s(%s)->%s" % (h[1], h[2], names.get(h[0])) for h in p["hits"]}),
        }
        (imported if entry["source_building_candidates"] or p["building_id"] is not None
         else unmatched).append(entry)
    return {"building_id": bid, "name": names.get(bid),
            "confirmed_assets": confirmed_assets, "confirmed_services": confirmed_services,
            "suspect_imports": imported, "unmatched_or_ambiguous": unmatched}
