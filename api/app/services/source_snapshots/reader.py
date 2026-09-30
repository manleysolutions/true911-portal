"""Read a CSV / XLSX export into (sheet, header, rows) - no interpretation."""

from __future__ import annotations

import csv
import os
from typing import Callable

MIN_HEADER_CELLS = 3


class ReadError(ValueError):
    pass


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return v                                  # keep datetimes / numbers typed


def _split(rows) -> tuple[list[str], list[list]]:
    header, data = None, []
    for r in rows:
        cells = [_cell(c) for c in r]
        if header is None:
            if sum(1 for c in cells if c not in ("", None)) >= MIN_HEADER_CELLS:
                header = [str(c) for c in cells]
            continue
        if any(c not in ("", None) for c in cells):
            data.append(cells)
    return header or [], data


def read_table(path: str, accept: Callable[[list[str]], bool]) -> tuple[str, list[str], list[list]]:
    """-> (sheet name, header, data rows).  For a workbook the first sheet whose
    header ``accept`` recognises is used; blank rows are skipped."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as fh:
            header, data = _split(csv.reader(fh))
        if not accept(header):
            raise ReadError("CSV header not recognised for this source: %s" % header[:12])
        return "csv", header, data
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            seen = []
            for ws in wb.worksheets:
                header, data = _split(ws.iter_rows(values_only=True))
                seen.append(ws.title)
                if header and accept(header):
                    return ws.title, header, data
        finally:
            wb.close()
        raise ReadError("no sheet with a recognised header for this source (sheets: %s)"
                        % ", ".join(seen))
    raise ReadError("unsupported file type '%s' (use .csv or .xlsx)" % ext)
