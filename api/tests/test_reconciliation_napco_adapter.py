"""EPIC-GEN-003 — NAPCO adapter tests (synthetic data only; no real customer data)."""

from __future__ import annotations

import json

from app.services.inventory_reconciliation.adapters import base, napco

# Synthetic NAPCO Radiolist (tab-delimited) — shape only, fabricated values.
_TSV = (
    "RadioNumber\tICCID\tDealerId\tSubscriberName\tDealerCompany\tDealerEmail\tSIMStatus\n"
    "10107087\t89148000007194217721\t9493400088\tAcme #351 Beverly Modern\tManley Solutions\tbilling@example.com\tActive\n"
    "10719648\t89148000007459957854\t9493400088\tAcme 632 Vero Beach\tManley Solutions\tbilling@example.com\tActive\n"
)


def test_parse_tsv_maps_canonical_fields():
    recs = napco.parse_text(_TSV)
    assert len(recs) == 2
    assert recs[0].vendor == "napco"
    assert recs[0].radio_number == "10107087"
    assert recs[0].iccid == "89148000007194217721"
    assert recs[0].subscriber_name == "Acme #351 Beverly Modern"
    assert recs[0].site_hint == recs[0].subscriber_name


def test_parse_csv_variant():
    recs = napco.parse_text(_TSV.replace("\t", ","))
    assert len(recs) == 2 and recs[1].iccid == "89148000007459957854"


def test_no_sensitive_fields_retained():
    recs = napco.parse_text(_TSV)
    blob = json.dumps([r.raw for r in recs])
    # carrier account / dealer email must NOT be carried into the canonical record
    assert "9493400088" not in blob and "billing@example.com" not in blob
    assert "sim_status" in blob  # only the non-sensitive extra is kept


def test_skips_blank_rows():
    assert len(napco.parse_text(_TSV + "\n\n")) == 2


def test_rows_without_keys_dropped():
    bad = "RadioNumber\tICCID\tSubscriberName\n\t\tNo identifiers here\n"
    assert napco.parse_text(bad) == []


def test_registered_in_adapter_registry():
    assert "napco" in base.available()
    adapter = base.get_adapter("napco")
    assert adapter is not None and adapter.vendor == "napco"
