"""Source adapters: one versioned parser per operational evidence source.

Headers are matched EXACTLY after normalisation (lower-case, alphanumerics
only) against each adapter's alias list, so "SIMStatus" never matches "SIM".
Identifiers are validated; malformed ones (spreadsheet scientific notation,
wrong length) are dropped with a recorded issue - never guessed or repaired.
Only allow-listed attributes are kept; contact / dealer / central-station
account numbers are never stored (a central-station receiver is reduced to a
"configured" boolean).  A hash of the full raw row is kept so a persisted
record can later be proven against the source file without storing it.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from app.services.canonical.normalize import n10, nid
from app.services.source_snapshots import status as ST

MSISDN, ICCID, IMEI, NAPCO_RADIO = "MSISDN", "ICCID", "IMEI", "NAPCO_RADIO"
IDENT_FIELDS = {"msisdn": MSISDN, "iccid": ICCID, "imei": IMEI, "napco_radio": NAPCO_RADIO}


def hkey(h) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h or "").lower())


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def parse_datetime(value) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = _text(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
                "%m/%d/%Y %I:%M %p", "%m/%d/%Y", "%m/%d/%y %H:%M", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _sci(v: str) -> bool:
    return bool(re.search(r"\d[.,]\d*e[+-]?\d+", v.lower()))


def validate_identifier(kind: str, raw) -> tuple[Optional[str], Optional[str]]:
    """-> (normalised value, issue).  Invalid -> (None, issue); absent -> (None, None)."""
    v = _text(raw)
    if not v or v in ("-", "n/a", "N/A", "none", "None"):
        return None, None
    if _sci(v):
        return None, "%s_MANGLED" % kind.upper()
    if kind == "msisdn":
        n = n10(v)
        return (n, None) if n else (None, "MSISDN_INVALID")
    x = nid(v)
    if kind == "imei":
        return (x, None) if x.isdigit() and 14 <= len(x) <= 16 else (None, "IMEI_INVALID")
    if kind == "iccid":
        if re.fullmatch(r"\d{18,22}F?", x):
            return x, None
        # NAPCO reports 20-char alphanumeric SIM ids for 3G:CDMA radios - a real,
        # deterministic identifier, kept but flagged (never "repaired")
        if re.fullmatch(r"[A-Z0-9]{18,22}", x):
            return x, "ICCID_NONSTANDARD"
        return None, "ICCID_INVALID"
    return (x, None) if x else (None, "NAPCO_RADIO_INVALID")


@dataclass
class ParsedRow:
    row_number: int
    identifiers: dict                    # msisdn / iccid / imei / napco_radio -> normalised
    record_key: Optional[str]
    identifier_type: Optional[str]
    status_raw: Optional[str]
    activity_at: Optional[datetime]
    location_hint: Optional[str]
    attributes: dict
    issues: list
    row_hash: str
    labels: list = field(default_factory=list)


@dataclass
class Adapter:
    source_system: str
    source_label: str
    parser_name: str
    parser_version: str
    columns: dict                         # field -> accepted normalised headers
    key_order: tuple
    recognise: Callable[[set], bool]
    attribute_fields: tuple = ()
    label_fields: tuple = ()
    activity_fields: tuple = ()
    derived: Callable[[dict], dict] = lambda values: {}
    effective_from_filename: Callable[[str], Optional[datetime]] = lambda name: None
    provisional: bool = False
    # headers that identify ANOTHER source's export - their presence rejects the
    # file, so e.g. a NAPCO RadioList can never be imported as a carrier file
    foreign_headers: tuple = ()

    def column_map(self, header: list[str]) -> dict:
        keys = [hkey(h) for h in header]
        out = {}
        for fld, aliases in self.columns.items():
            for a in aliases:
                if a in keys:
                    out[fld] = keys.index(a)
                    break
        return out

    def accepts(self, header: list[str]) -> bool:
        if set(self.foreign_headers) & {hkey(h) for h in header}:
            return False
        return self.recognise(set(self.column_map(header)))

    def parse(self, header: list[str], row: list, row_number: int, cmap: dict) -> ParsedRow:
        values = {f: (row[i] if i < len(row) else "") for f, i in cmap.items()}
        issues, idents = [], {}
        for fld in IDENT_FIELDS:
            if fld in values:
                val, issue = validate_identifier(fld, values[fld])
                if val:
                    idents[fld] = val
                if issue:
                    issues.append(issue)
        key_field = next((f for f in self.key_order if f in idents), None)
        labels = [_text(values[f]) for f in self.label_fields if _text(values.get(f))]
        activity = None
        for f in self.activity_fields:
            activity = parse_datetime(values.get(f))
            if activity:
                break
        attrs = {f: _text(values[f]) for f in self.attribute_fields if _text(values.get(f))}
        attrs.update(self.derived(values))
        if issues:
            attrs["identifier_issues"] = sorted(set(issues))
        raw = {str(h): _text(row[i] if i < len(row) else "") for i, h in enumerate(header)}
        row_hash = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        return ParsedRow(
            row_number=row_number, identifiers=idents,
            record_key=idents.get(key_field) if key_field else None,
            identifier_type=IDENT_FIELDS[key_field] if key_field else None,
            status_raw=_text(values.get("status")) or None, activity_at=activity,
            location_hint=(labels[0][:255] if labels else None), attributes=attrs,
            issues=issues, row_hash=row_hash, labels=labels)


# ── NAPCO StarLink RadioList ─────────────────────────────────────────

def _napco_derived(values: dict) -> dict:
    def configured(v):
        return _text(v) not in ("", "-")
    out = {}
    if "primary_cs" in values:
        out["primary_cs_configured"] = configured(values["primary_cs"])
    if "backup_cs" in values:
        out["backup_cs_configured"] = configured(values["backup_cs"])
    return out


def _napco_effective(name: str) -> Optional[datetime]:
    m = re.search(r"radiolist[-_](\d{14})", name.lower())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


NAPCO_ADAPTER = Adapter(
    source_system=ST.NAPCO, source_label="NAPCO StarLink RadioList",
    parser_name="napco_radiolist", parser_version="napco_radiolist.v1",
    columns={
        "napco_radio": ("radionumber",), "iccid": ("iccid",), "status": ("simstatus",),
        "activity": ("lastsignalreceived",), "label": ("subscribername",),
        "online_date": ("onlinedate",), "firmware": ("firmwarever",),
        "debounce": ("debouncetime",), "polling": ("pollingrate",), "plan": ("plan",),
        "gen_tech": ("gentech",), "primary_cs_type": ("primarycsreceivertype",),
        "backup_cs_type": ("backupcsreceivertype",), "primary_cs": ("primarycsreceiver",),
        "backup_cs": ("backupcsreceiver",),
    },
    key_order=("napco_radio",),
    recognise=lambda f: {"napco_radio", "status"} <= f,
    attribute_fields=("online_date", "firmware", "debounce", "polling", "plan", "gen_tech",
                      "primary_cs_type", "backup_cs_type"),
    label_fields=("label",), activity_fields=("activity",),
    derived=_napco_derived, effective_from_filename=_napco_effective,
)

_ADDR = {"street": ("street", "streetaddress", "address", "siteaddress", "facilityaddress"),
         "city": ("city", "sitecity", "facilitycity"),
         "state": ("state", "sitestate", "facilitystate"),
         "zip": ("zip", "zipcode", "sitezip", "postalcode", "facilityzipcode")}


_NAPCO_SIGNATURE = ("radionumber", "dealerid", "primarycsreceiver")


def _carrier_recognise(f: set) -> bool:
    return bool(f & {"msisdn", "iccid", "imei"}) and bool(f & {"status", "label"})


# ── T-Mobile / Infatrac (Genesis) ────────────────────────────────────
TMOBILE_ADAPTER = Adapter(
    source_system=ST.T_MOBILE, source_label="T-Mobile / Infatrac inventory",
    parser_name="tmobile_infatrac", parser_version="tmobile_infatrac.v1",
    columns=dict({
        "msisdn": ("msisdn", "phonenumber", "phone", "mdn", "subscribernumber", "did"),
        "iccid": ("iccid", "simiccid", "sim", "simnumber"),
        "imei": ("imei", "deviceimei"),
        "status": ("status", "subscriberstatus", "activationstatus", "linestatus", "simstatus"),
        "label": ("label", "description", "accountname", "sitename", "subscribername",
                  "customername", "name", "locationname"),
        "model": ("model", "devicemodel", "hardwaremodel"),
        "plan": ("plan", "rateplan", "priceplan"),
        "activation_date": ("activationdate", "activatedon", "activated"),
        "activity": ("lastactivity", "lastusage", "lastseen", "lastconnection"),
    }, **_ADDR),
    key_order=("msisdn", "iccid", "imei"), recognise=_carrier_recognise,
    attribute_fields=("model", "plan", "activation_date", "street", "city", "state", "zip"),
    label_fields=("label",), activity_fields=("activity",), foreign_headers=_NAPCO_SIGNATURE,
)

# ── Verizon ThingSpace ───────────────────────────────────────────────
VERIZON_ADAPTER = Adapter(
    source_system=ST.VERIZON, source_label="Verizon ThingSpace inventory",
    parser_name="verizon_thingspace", parser_version="verizon_thingspace.v1",
    columns=dict({
        "msisdn": ("mdn", "msisdn", "phonenumber", "mobilenumber"),
        "iccid": ("iccid", "simiccid", "sim"),
        "imei": ("imei", "imeimeid", "deviceimei"),
        "status": ("state", "status", "linestate", "devicestate", "subscriptionstate"),
        "label": ("costcentername", "costcenter", "devicename", "devicelabel", "groupname",
                  "accountname", "customername", "label"),
        "model": ("model", "devicemodel"),
        "plan": ("serviceplan", "rateplan", "plan"),
        "activation_date": ("lastactivationdate", "activationdate"),
        "activity": ("lastconnectiondate", "lastconnectiontime", "lastactivitydate"),
    }, **_ADDR),
    key_order=("msisdn", "iccid", "imei"), recognise=_carrier_recognise,
    attribute_fields=("model", "plan", "activation_date", "street", "city", "state", "zip"),
    label_fields=("label",), activity_fields=("activity",), foreign_headers=_NAPCO_SIGNATURE,
)

# ── Red Pocket (contract only until a production export is reviewed) ─
REDPOCKET_ADAPTER = Adapter(
    source_system=ST.RED_POCKET, source_label="Red Pocket inventory (provisional)",
    parser_name="redpocket", parser_version="redpocket.v0-provisional",
    columns={
        "msisdn": ("phonenumber", "phone", "mdn", "msisdn", "number", "line"),
        "iccid": ("iccid", "sim", "simnumber", "simcard"),
        "imei": ("imei",),
        "status": ("status", "linestatus", "accountstatus"),
        "label": ("nickname", "label", "name", "description", "accountname"),
        "plan": ("plan", "planname"),
        "expiry": ("expirationdate", "expiry", "renewaldate", "planexpiration"),
    },
    key_order=("msisdn", "iccid", "imei"), recognise=_carrier_recognise,
    attribute_fields=("plan", "expiry"), label_fields=("label",), provisional=True,
    foreign_headers=_NAPCO_SIGNATURE,
)

ADAPTERS = {a.source_system: a for a in (NAPCO_ADAPTER, TMOBILE_ADAPTER, VERIZON_ADAPTER,
                                         REDPOCKET_ADAPTER)}
