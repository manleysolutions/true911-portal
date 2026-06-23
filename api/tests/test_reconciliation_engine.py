"""EPIC-GEN-003 — reconciliation engine tests (pure, vendor/customer-agnostic)."""

from __future__ import annotations

from app.services.inventory_reconciliation import engine
from app.services.inventory_reconciliation.models import True911Item, VendorRecord


def _item(device_id, iccid=None, radio=None, site_id=None, site_name=None,
          customer="Acme", su=None, e911=None, tel=None):
    return True911Item(device_id=device_id, iccid=iccid, radio_number=radio, site_id=site_id,
                       site_name=site_name, customer_name=customer, service_unit_id=su,
                       e911_status=e911, last_telemetry=tel)


def _vr(iccid=None, radio=None, sub=None, site=None):
    return VendorRecord(vendor="napco", radio_number=radio, iccid=iccid,
                        subscriber_name=sub, site_hint=site)


# ── Hierarchy 1: ICCID ───────────────────────────────────────────────
def test_iccid_full_linkage_matched():
    items = [_item("D1", iccid="8901240204219434247", site_id="S1", site_name="Boston", su="SU-D1", e911="validated")]
    rows, summary = engine.reconcile([_vr(iccid="8901240204219434247", sub="Acme #351")], items)
    r = rows[0]
    assert r.result == "MATCHED" and r.confidence == 1.0
    assert r.true911_device_id == "D1" and r.service_unit_id == "SU-D1"
    assert summary["matched"] == 1 and summary["match_rate"] == 1.0


def test_iccid_partial_when_no_service_unit():
    items = [_item("D1", iccid="89012402042194342470", site_id="S1", site_name="X")]
    rows, _ = engine.reconcile([_vr(iccid="89012402042194342470")], items)
    assert rows[0].result == "PARTIAL" and "no service unit" in rows[0].notes


def test_iccid_normalized_match():
    items = [_item("D1", iccid="8901240204219434247", site_id="S", su="U")]
    rows, _ = engine.reconcile([_vr(iccid="8901-2402 0421 9434247")], items)
    assert rows[0].result == "MATCHED"


def test_iccid_beats_radionumber():
    items = [_item("A", iccid="111", radio="999", site_id="S", su="U"), _item("B", radio="888")]
    rows, _ = engine.reconcile([_vr(iccid="111", radio="888")], items)
    vrow = [r for r in rows if r.iccid == "111"][0]
    assert vrow.true911_device_id == "A"


# ── Hierarchy 2: RadioNumber ─────────────────────────────────────────
def test_radio_match_when_no_iccid():
    items = [_item("D1", radio="10000001", site_id="S1", su="SU1")]
    rows, _ = engine.reconcile([_vr(radio="10000001")], items)
    assert rows[0].result == "MATCHED" and rows[0].confidence == 0.9


def test_radio_leading_zero_normalized():
    items = [_item("D1", radio="10000001", site_id="S", su="U")]
    rows, _ = engine.reconcile([_vr(radio="0010000001")], items)
    assert rows[0].result == "MATCHED"


# ── Hierarchy 3 & 4: name / site → REVIEW ────────────────────────────
def test_subscribername_exact_normalized_review():
    items = [_item("D1", customer="Acme", site_name="351 Beverly")]
    rows, _ = engine.reconcile([_vr(sub="Acme 351 Beverly")], items)
    assert rows[0].result == "REVIEW" and rows[0].confidence == 0.6


def test_site_similarity_review():
    items = [_item("D1", customer="Acme", site_name="Beverly Modern Store 351")]
    rows, _ = engine.reconcile([_vr(sub="Acme Beverly Modern")], items)
    assert rows[0].result == "REVIEW"


# ── MISSING (both directions) ────────────────────────────────────────
def test_missing_in_true911():
    items = [_item("D1", iccid="111", site_id="S", su="U")]
    rows, _ = engine.reconcile([_vr(iccid="999", sub="Totally Different Co")], items)
    vrow = [r for r in rows if r.iccid == "999"][0]
    assert vrow.result == "MISSING_IN_TRUE911"


def test_missing_in_vendor_reverse_pass():
    items = [_item("D1", iccid="111", site_id="S", su="U")]
    rows, summary = engine.reconcile([], items)
    assert rows[0].result == "MISSING_IN_VENDOR" and summary["missing_in_vendor"] == 1


# ── DUPLICATE ────────────────────────────────────────────────────────
def test_vendor_duplicate_iccid():
    rows, summary = engine.reconcile([_vr(iccid="111", radio="A"), _vr(iccid="111", radio="B")], [])
    assert all(r.result == "DUPLICATE" for r in rows) and summary["duplicate"] == 2


def test_iccid_matches_multiple_devices_duplicate():
    items = [_item("D1", iccid="111"), _item("D2", iccid="111")]
    rows, _ = engine.reconcile([_vr(iccid="111")], items)
    r = rows[0]
    assert r.result == "DUPLICATE" and "D1" in r.true911_device_id and "D2" in r.true911_device_id
    assert len(rows) == 1  # both items consumed; no MISSING_IN_VENDOR


# ── Summary ──────────────────────────────────────────────────────────
def test_summary_counts_and_match_rate():
    items = [_item("D1", iccid="111", site_id="S", su="U"), _item("D2", radio="r2")]
    rows, summary = engine.reconcile(
        [_vr(iccid="111"), _vr(iccid="zzz", sub="Nope Co")], items)
    assert summary["vendor_records"] == 2
    assert summary["matched"] == 1 and summary["missing_in_true911"] == 1
    assert summary["missing_in_vendor"] == 1  # D2 unmatched
    assert summary["match_rate"] == 0.5
