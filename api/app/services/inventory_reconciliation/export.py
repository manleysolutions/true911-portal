"""CSV + JSON export for reconciliation results."""

from __future__ import annotations

import csv
import io
import json

from app.services.inventory_reconciliation.models import CSV_COLUMNS, ReconRow


def rows_to_csv(rows: list[ReconRow]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for r in rows:
        w.writerow([
            r.customer, r.site, r.radio_number, r.iccid, r.subscriber_name,
            r.true911_device_id, r.true911_site, r.true911_customer, r.service_unit_id,
            r.e911_status, r.last_telemetry, r.confidence, r.result, r.notes,
        ])
    return buf.getvalue()


def rows_to_json(rows: list[ReconRow], summary: dict) -> str:
    return json.dumps({"summary": summary, "rows": [r.__dict__ for r in rows]},
                      indent=2, default=str)


def write_reports(base_path: str, rows: list[ReconRow], summary: dict) -> tuple[str, str]:
    """Write ``<base>.csv`` + ``<base>.json``; returns their paths."""
    stem = base_path[:-4] if base_path.lower().endswith(".csv") else base_path
    csv_path, json_path = stem + ".csv", stem + ".json"
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(rows_to_csv(rows))
    with open(json_path, "w", encoding="utf-8") as fh:
        fh.write(rows_to_json(rows, summary))
    return csv_path, json_path
