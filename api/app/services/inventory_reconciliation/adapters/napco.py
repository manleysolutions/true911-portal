"""NAPCO StarLink Radiolist adapter — the first reconciliation vendor adapter.

Parses a NAPCO Radiolist export (tab- or comma-delimited text; .xlsx via openpyxl
if available) into canonical VendorRecords. Maps only the fields the engine needs
(RadioNumber, ICCID, SubscriberName) — carrier account numbers, CS receiver phone
numbers, dealer email, etc. are deliberately NOT retained, so reconciliation
artifacts never carry sensitive monitoring data.
"""

from __future__ import annotations

import csv
import io

from app.services.inventory_reconciliation.adapters import base
from app.services.inventory_reconciliation.models import VendorRecord

VENDOR = "napco"


def _delimiter(sample: str) -> str:
    return "\t" if sample.count("\t") >= sample.count(",") else ","


def parse_text(text: str) -> list[VendorRecord]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    reader = csv.DictReader(io.StringIO(text), delimiter=_delimiter(lines[0]))
    out: list[VendorRecord] = []
    for row in reader:
        norm = {(k or "").strip().lower().replace(" ", ""): (v or "").strip() for k, v in row.items()}
        radio = norm.get("radionumber") or None
        iccid = norm.get("iccid") or None
        subscriber = norm.get("subscribername") or None
        if not (radio or iccid):
            continue
        out.append(VendorRecord(
            vendor=VENDOR,
            radio_number=radio,
            iccid=iccid,
            subscriber_name=subscriber,
            customer_hint=None,             # derived generically by the engine
            site_hint=subscriber,           # NAPCO subscriber name doubles as the site label
            raw={"sim_status": norm.get("simstatus") or None},  # non-sensitive only
        ))
    return out


def parse_xlsx(path: str) -> list[VendorRecord]:
    import openpyxl  # optional dependency; only imported when an .xlsx is given
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h or "").strip() for h in rows[0]]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t")
    w.writerow(header)
    for r in rows[1:]:
        w.writerow(["" if c is None else str(c) for c in r])
    return parse_text(buf.getvalue())


def parse(path: str) -> list[VendorRecord]:
    if path.lower().endswith(".xlsx"):
        return parse_xlsx(path)
    with open(path, "r", encoding="utf-8-sig") as fh:
        return parse_text(fh.read())


class NapcoAdapter:
    vendor = VENDOR

    @staticmethod
    def parse(path: str) -> list[VendorRecord]:
        return parse(path)


base.register(VENDOR, NapcoAdapter())
