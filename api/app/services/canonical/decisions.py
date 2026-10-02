"""Operator-decision ledger (D-023, Decision 2).

Operator ground truth is supplied in an EXTERNAL JSON file (never committed to
the repository) and recorded as durable, auditable, reversible rows in
``operator_decisions``.  A changed decision never edits or deletes the earlier
one: the new row carries the earlier ``new_state`` as its ``previous_state`` and
the earlier row is marked ``superseded_by_id`` / ``superseded_at``.  Reversal is
simply a newer decision.  Re-recording an identical decision is a no-op.

Input file shape::

    {"tenant": "<tenant_id>",
     "decisions": [
        {"type": "BUILDING_IDENTITY_SUSPECT",
         "subject": {"building": "<canonical building name>"},
         "new_state": {"suspect": true},
         "effective_date": "2026-09-01",
         "reason": "<why>"},
        ...]}

A subject names its building by ``building`` (exact canonical name) or
``building_id``.  See docs/customer/CANONICAL_SERVICE_MODEL.md for every type.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.services.canonical import vocab as V
from app.services.canonical.normalize import n10, nid, radio_id


class DecisionError(ValueError):
    pass


_SERVICE_CLASSES = (V.ELEVATOR, V.EMERGENCY_PHONE, V.FACP_ASSET, V.OTHER, V.UNCLASSIFIED)


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(entry: dict) -> str:
    return hashlib.sha256(_canon(entry).encode()).hexdigest()


def resolve_building(subject: dict, buildings: list[dict]) -> int:
    """Building id from ``building_id`` or an exact (case-insensitive) name."""
    if subject.get("building_id") is not None:
        try:
            bid = int(subject["building_id"])
        except (TypeError, ValueError):
            raise DecisionError("building_id must be an integer")
        if not any(b["id"] == bid for b in buildings):
            raise DecisionError("building_id %s is not a building of this tenant" % bid)
        return bid
    name = str(subject.get("building") or "").strip().lower()
    if not name:
        raise DecisionError("subject needs 'building' or 'building_id'")
    hits = [b["id"] for b in buildings if str(b.get("name") or "").strip().lower() == name]
    if len(hits) != 1:
        raise DecisionError("building '%s' matched %d buildings (need exactly 1)"
                            % (subject.get("building"), len(hits)))
    return hits[0]


def _numbers(values, what) -> list[str]:
    if not isinstance(values, list) or not values:
        raise DecisionError("%s must be a non-empty list of telephone numbers" % what)
    out = []
    for v in values:
        n = n10(v)
        if not n:
            raise DecisionError("%s: '%s' is not a 10-digit telephone number" % (what, v))
        out.append(n)
    if len(set(out)) != len(out):
        raise DecisionError("%s contains duplicates" % what)
    return sorted(out)


def _radios(values) -> list[str]:
    if not isinstance(values, list) or not values:
        raise DecisionError("radios must be a non-empty list of communicator radio ids")
    out = []
    for v in values:
        r = radio_id(v)
        if not r:
            raise DecisionError("radios: '%s' is not a radio id (serial / IMEI / ICCID / "
                                "telephone shapes are refused)" % v)
        out.append(r)
    if len(set(out)) != len(out):
        raise DecisionError("radios contains duplicates")
    return sorted(out)


def _ref(subject, field, dtype) -> str:
    ref = str(subject.get(field) or "").strip()
    if not ref:
        raise DecisionError("%s: subject.%s is required (a stable operator handle, e.g. "
                            "'FACP 1')" % (dtype, field))
    return ref


def _date(value):
    if value in (None, ""):
        return None
    try:
        d = datetime.fromisoformat(str(value))
    except ValueError:
        raise DecisionError("effective_date '%s' is not ISO-8601" % value)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def normalize_entry(entry: dict, buildings: list[dict]) -> dict:
    """Validate one input entry -> a normalised decision (subject resolved to
    ids / normalised values, deterministic ``decision_key``).  Raises
    DecisionError with an operator-readable message."""
    if not isinstance(entry, dict):
        raise DecisionError("each decision must be an object")
    dtype = str(entry.get("type") or entry.get("decision_type") or "").strip().upper()
    if dtype not in V.DECISION_TYPES:
        raise DecisionError("unknown decision type '%s'" % dtype)
    subject = dict(entry.get("subject") or {})
    new_state = dict(entry.get("new_state") or {})
    reason = str(entry.get("reason") or "").strip()
    if not reason:
        raise DecisionError("%s: a reason is required" % dtype)

    if dtype == V.D_BUILDING_IDENTITY_SUSPECT:
        bid = resolve_building(subject, buildings)
        subj = {"building_id": bid}
        state = {"suspect": bool(new_state.get("suspect", True))}
        key = "%s:b%d" % (dtype, bid)
    elif dtype == V.D_CARRIER_MIGRATION:
        bid = resolve_building(subject, buildings)
        legacy = _numbers(subject.get("legacy_numbers"), "legacy_numbers")
        repl = _numbers(subject.get("replacement_numbers"), "replacement_numbers")
        if set(legacy) & set(repl):
            raise DecisionError("a number cannot be both legacy and replacement")
        subj = {"building_id": bid, "legacy_numbers": legacy, "replacement_numbers": repl}
        state = {
            "legacy_lifecycle": str(new_state.get("legacy_lifecycle") or V.DECOMMISSIONED).upper(),
            "replacement_lifecycle": str(new_state.get("replacement_lifecycle") or V.CURRENT).upper(),
            "legacy_carrier": new_state.get("legacy_carrier"),
            "replacement_carrier": new_state.get("replacement_carrier"),
        }
        for k in ("legacy_lifecycle", "replacement_lifecycle"):
            if state[k] not in V.LIFECYCLES:
                raise DecisionError("%s '%s' is not a lifecycle" % (k, state[k]))
        tag = hashlib.sha256(",".join(legacy).encode()).hexdigest()[:10]
        key = "%s:b%d:%s" % (dtype, bid, tag)
    elif dtype == V.D_ASSET_LIFECYCLE:
        atype = str(subject.get("asset_type") or V.TELEPHONE_NUMBER).upper()
        if atype not in V.ASSET_TYPES:
            raise DecisionError("asset_type '%s' unknown" % atype)
        value = n10(subject.get("value")) if atype == V.TELEPHONE_NUMBER else nid(subject.get("value"))
        if not value:
            raise DecisionError("ASSET_LIFECYCLE: subject.value is not a valid %s" % atype)
        lc = str(new_state.get("lifecycle") or "").upper()
        if lc not in V.LIFECYCLES:
            raise DecisionError("lifecycle '%s' unknown" % lc)
        subj = {"asset_type": atype, "value": value}
        state = {"lifecycle": lc, "reason": new_state.get("reason") or V.REASON_OPERATOR}
        key = "%s:%s:%s" % (dtype, atype, value)
    elif dtype == V.D_SERVICE_CLASSIFICATION:
        bid = resolve_building(subject, buildings)
        n = n10(subject.get("number"))
        if not n:
            raise DecisionError("SERVICE_CLASSIFICATION: subject.number is not a telephone number")
        st = str(new_state.get("service_type") or "").upper()
        if st not in _SERVICE_CLASSES:
            raise DecisionError("service_type '%s' must be one of %s" % (st, ", ".join(_SERVICE_CLASSES)))
        subj = {"building_id": bid, "number": n}
        state = {"service_type": st, "label": new_state.get("label")}
        key = "%s:b%d:%s" % (dtype, bid, n)
    elif dtype == V.D_FACP_SERVICE:
        # the radio set lives in new_state so a changed set SUPERSEDES the
        # decision (the key is the stable operator handle)
        bid = resolve_building(subject, buildings)
        ref = _ref(subject, "service_ref", dtype)
        subj = {"building_id": bid, "service_ref": ref}
        state = {"radios": _radios(new_state.get("radios")), "label": new_state.get("label")}
        key = "%s:b%d:%s" % (dtype, bid, ref.upper())
    elif dtype == V.D_SOURCE_RECORD:
        src = str(subject.get("source") or "").strip().upper()
        if src not in (V.SRC_ZOHO, V.SRC_TRUE911):
            raise DecisionError("SOURCE_RECORD: subject.source must be ZOHO or TRUE911")
        rec = str(subject.get("record_id") or "").strip()
        if not rec:
            raise DecisionError("SOURCE_RECORD: subject.record_id is required")
        disp = str(new_state.get("disposition") or "").strip().upper()
        if disp not in V.RECORD_DISPOSITIONS:
            raise DecisionError("disposition '%s' must be one of %s"
                                % (disp, ", ".join(V.RECORD_DISPOSITIONS)))
        state = {"disposition": disp, "duplicate_of": new_state.get("duplicate_of")}
        if disp == V.REC_OUTSIDE:
            loc = str(new_state.get("location") or "").strip()
            if not loc:
                raise DecisionError("OUTSIDE_PORTFOLIO: new_state.location is required")
            state["location"] = loc
        if disp == V.REC_BUILDING:
            state["building_id"] = resolve_building(new_state, buildings)
        subj = {"source": src, "record_id": rec}
        key = "%s:%s:%s" % (dtype, src, rec)
    elif dtype == V.D_SERVICE_POOL:
        bid = resolve_building(subject, buildings)
        ref = _ref(subject, "pool_ref", dtype)
        alias = {"FAX": V.OTHER, "OTHER": V.OTHER, "EPH": V.EMERGENCY_PHONE}
        types = sorted({alias.get(str(t).strip().upper(), str(t).strip().upper())
                        for t in new_state.get("service_types") or []})
        if not types or any(t not in V.POOL_SERVICE_TYPES for t in types):
            raise DecisionError("service_types must be a non-empty subset of %s"
                                % ", ".join(V.POOL_SERVICE_TYPES))
        subj = {"building_id": bid, "pool_ref": ref}
        state = {"numbers": _numbers(new_state.get("numbers"), "numbers"),
                 "service_types": types, "label": new_state.get("label")}
        key = "%s:b%d:%s" % (dtype, bid, ref.upper())
    else:  # SERVICE_APPROVAL
        bid = resolve_building(subject, buildings)
        skey = str(subject.get("service_key") or "").strip()
        if not skey:
            raise DecisionError("SERVICE_APPROVAL: subject.service_key is required")
        ap = str(new_state.get("approval") or "").upper()
        if ap not in V.APPROVALS:
            raise DecisionError("approval '%s' must be one of %s" % (ap, ", ".join(V.APPROVALS)))
        subj = {"building_id": bid, "service_key": skey}
        state = {"approval": ap}
        key = "%s:b%d:%s" % (dtype, bid, skey)

    return {"decision_type": dtype, "decision_key": key, "subject": subj,
            "new_state": state, "effective_date": _date(entry.get("effective_date")),
            "reason": reason, "input_fingerprint": fingerprint(entry)}


def parse_file(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("decisions"), list):
        raise DecisionError("decision file must be an object with a 'decisions' list")
    return data


def normalize_all(entries: list, buildings: list[dict]) -> tuple[list[dict], list[str]]:
    """-> (normalised decisions, errors).  Two entries with the same key in one
    file are an error (the operator must say which one holds)."""
    out, errors, seen = [], [], {}
    for i, e in enumerate(entries):
        try:
            d = normalize_entry(e, buildings)
        except DecisionError as exc:
            errors.append("decision #%d: %s" % (i + 1, exc))
            continue
        if d["decision_key"] in seen:
            errors.append("decision #%d duplicates decision #%d (%s)"
                          % (i + 1, seen[d["decision_key"]] + 1, d["decision_type"]))
            continue
        seen[d["decision_key"]] = i
        out.append(d)
    return out, errors


def overlay(active: list[dict], proposed: list[dict]) -> list[dict]:
    """The decision set that WOULD be in force if ``proposed`` were recorded
    (dry-run preview): proposed entries replace active ones with the same key."""
    keys = {d["decision_key"] for d in proposed}
    return [d for d in active if d["decision_key"] not in keys] + list(proposed)


# ── persistence ─────────────────────────────────────────────────────────

def _row_to_dict(r) -> dict:
    return {"id": r.id, "decision_type": r.decision_type, "decision_key": r.decision_key,
            "subject": json.loads(r.subject or "{}"),
            "new_state": json.loads(r.new_state or "{}"),
            "effective_date": r.effective_date, "reason": r.reason,
            "recorded_by": r.recorded_by, "recorded_at": r.recorded_at}


async def load_active(db, tenant_id: str) -> list[dict]:
    from sqlalchemy import select

    from app.models.canonical import OperatorDecision
    rows = (await db.execute(select(OperatorDecision).where(
        OperatorDecision.tenant_id == tenant_id,
        OperatorDecision.superseded_by_id.is_(None)).order_by(OperatorDecision.id))).scalars().all()
    return [_row_to_dict(r) for r in rows]


async def load_history(db, tenant_id: str) -> list[dict]:
    from sqlalchemy import select

    from app.models.canonical import OperatorDecision
    rows = (await db.execute(select(OperatorDecision).where(
        OperatorDecision.tenant_id == tenant_id).order_by(OperatorDecision.id))).scalars().all()
    return [dict(_row_to_dict(r), superseded_by_id=r.superseded_by_id) for r in rows]


async def plan_and_record(db, tenant_id: str, decisions: list[dict], *, recorded_by: str,
                          apply: bool) -> list[dict]:
    """Compare normalised decisions with the active ledger.  Returns one plan row
    per decision: NEW / SUPERSEDE / UNCHANGED.  Writes (and commits) only when
    ``apply`` is True; never deletes or edits a prior decision's content."""
    from sqlalchemy import select

    from app.models.canonical import OperatorDecision

    now = datetime.now(timezone.utc)
    plan = []
    for d in decisions:
        prior = (await db.execute(select(OperatorDecision).where(
            OperatorDecision.tenant_id == tenant_id,
            OperatorDecision.decision_key == d["decision_key"],
            OperatorDecision.superseded_by_id.is_(None)))).scalars().first()
        new_state = _canon(d["new_state"])
        if prior is not None and prior.new_state == new_state:
            plan.append({"action": "UNCHANGED", "decision": d, "prior_id": prior.id})
            continue
        plan.append({"action": "SUPERSEDE" if prior else "NEW", "decision": d,
                     "prior_id": prior.id if prior else None,
                     "previous_state": json.loads(prior.new_state) if prior else None})
        if not apply:
            continue
        row = OperatorDecision(
            tenant_id=tenant_id, decision_type=d["decision_type"],
            decision_key=d["decision_key"], subject=_canon(d["subject"]),
            previous_state=prior.new_state if prior else None, new_state=new_state,
            effective_date=d["effective_date"], reason=d["reason"], source=V.SRC_OPERATOR,
            recorded_by=recorded_by, recorded_at=now,
            input_fingerprint=d["input_fingerprint"])
        db.add(row)
        await db.flush()
        if prior is not None:
            prior.superseded_by_id = row.id
            prior.superseded_at = now
        plan[-1]["new_id"] = row.id
    if apply:
        await db.commit()
    return plan
