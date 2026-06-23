"""PR-C1 — customer serializer guarantees (RH Go-Live Phase 3).

The core safety net for the whole /api/customer/* namespace:
  * sentinel-leak: no hidden identifier/telecom/internal field reaches output,
  * new-column safety: an unmapped attribute never appears (allow-list),
  * no-false-green: a "Protected" status without evidence is recoded to Unknown,
  * axis separation: the E911 mapper never emits operational/device health,
  * support: only customer_safe_summary is emitted (never internal_summary).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from app.models.site import Site
from app.models.device import Device
from app.models.service_unit import ServiceUnit
from app.models.subscription import Subscription
from app.models.support import SupportSession, SupportDiagnostic, SupportMessage
from app.services.customer import serialize as S

NOW = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)


def _dump(obj) -> str:
    return json.dumps(obj)


# ── Sentinel-leak: every hidden field set to "LEAK..." must not appear ──
def test_equipment_mapper_leaks_no_identifiers():
    d = Device(
        device_type="elevator_phone", status="active", last_heartbeat=NOW, activated_at=None,
        serial_number="LEAKSERIAL", mac_address="LEAKMAC", imei="LEAKIMEI", iccid="LEAKICCID",
        msisdn="LEAKMSISDN", imsi="LEAKIMSI", firmware_version="LEAKFW", container_version="LEAKCONT",
        provision_code="LEAKPROV", carrier="LEAKCARRIER", wan_ip="LEAKWAN", lan_ip="LEAKLAN",
        vola_org_id="LEAKVOLA", starlink_id="LEAKSTAR",
    )
    out = S.equipment_from_device(d, protection=S.status_object("Unknown", reason="x"))
    assert "LEAK" not in _dump(out)
    assert out["equipment"] == "Elevator phone unit"  # derived, raw model never shown


def test_equipment_mapper_new_column_safety():
    d = Device(device_type="fire_alarm", status="active", last_heartbeat=NOW)
    d.brand_new_secret_column = "LEAKNEW"  # unmapped attribute
    out = S.equipment_from_device(d, protection=S.status_object("Unknown", reason="x"))
    assert "LEAKNEW" not in _dump(out)


def test_location_mapper_leaks_no_telecom():
    s = Site(
        id=1, site_name="RH Yountville", building_type="Gallery",
        e911_street="6725 Washington St", e911_city="Yountville", e911_state="CA",
        e911_zip="94599", e911_status="validated", status="active",
        carrier="LEAKCARRIER", static_ip="LEAKIP", device_serial="LEAKSER",
        device_firmware="LEAKFW", csa_model="LEAKCSA", kit_type="LEAKKIT",
        psap_id="LEAKPSAP", ng911_uri="LEAKNG911", emergency_class="LEAKEC",
        address_source="LEAKSRC", notes="LEAKNOTES",
    )
    out = S.location_summary(s, protection=S.status_object("Unknown", reason="x"))
    assert "LEAK" not in _dump(out)
    assert out["location"] == "RH Yountville"
    assert out["location_ref"].startswith("loc_")


def test_service_mapper_leaks_no_linkage():
    u = ServiceUnit(
        id=1, unit_name="Elevator #1 Phone", unit_type="elevator_phone",
        location_description="Elevator #1", floor="1", voice_supported=True,
        compliance_status="compliant", governing_code_edition="ASME A17.1-2019",
        device_id="LEAKDEV", line_id="LEAKLINE", sim_id=999, notes="LEAKNOTES",
        video_stream_url="LEAKURL", video_transport_type="LEAKVT",
        jurisdiction_code="LEAKJUR", monitoring_station_type="LEAKMON",
    )
    out = S.service_from_unit(u, protection=S.status_object("Unknown", reason="x"))
    assert "LEAK" not in _dump(out)
    assert out["service"] == "Elevator emergency phone"


def test_billing_mapper_leaks_no_external_ids():
    sub = Subscription(
        plan_name="Emergency Line Monitoring", status="active", mrr=120.0, qty_lines=2,
        external_subscription_id="LEAKEXT", external_source="LEAKSRC",
    )
    out = S.billing_from_subscription(sub)
    assert "LEAK" not in _dump(out)
    assert out["monthly_cost"] == 120.0 and out["status"] == "Active"


# ── No false green ───────────────────────────────────────────────────
def test_protected_without_evidence_recoded_to_unknown():
    out = S.status_object("Protected", as_of=None, evidence=None)
    assert out["status"] == "Unknown" and "evidence" not in out


def test_protected_without_as_of_recoded_to_unknown():
    out = S.status_object("Protected", as_of=None, evidence=S.evidence_object(NOW.isoformat(), ["online"]))
    assert out["status"] == "Unknown"


def test_protected_with_evidence_stays_green():
    ev = S.evidence_object(NOW.isoformat(), ["device online", "test call 2026-07-10"])
    out = S.status_object("Protected", as_of=NOW.isoformat(), evidence=ev)
    assert out["status"] == "Protected" and out["evidence"]["signals"]


def test_unknown_label_normalized():
    assert S.status_object("TotallyBogus")["status"] == "Unknown"


def test_critical_has_reason_no_evidence_key():
    out = S.status_object("Critical", as_of=NOW.isoformat(), reason="Emergency address not verified")
    assert out["status"] == "Critical" and out["reason"] and "evidence" not in out


# ── Axis separation (D-006) ──────────────────────────────────────────
def test_e911_mapper_is_address_axis_only():
    s = Site(id=2, site_name="RH Boston", e911_street="234 Berkeley St", e911_city="Boston",
             e911_state="MA", e911_zip="02116", e911_status="pending", status="active",
             e911_confirmation_required=False, psap_id="LEAKPSAP", ng911_uri="LEAKNG")
    out = S.e911_summary(s)
    blob = _dump(out)
    assert "LEAK" not in blob
    # active + unverified => Critical-by-rule, surfaced on the E911 axis only
    assert out["verification"]["is_critical"] is True
    assert out["verification"]["state"] == "Not yet verified"
    # never leaks operational/device health into the E911 axis
    for forbidden in ("protection", "health", "equipment", "last_seen", "heartbeat"):
        assert forbidden not in out


def test_e911_verified_active_is_not_critical():
    s = Site(id=3, site_name="RH Yountville", e911_street="6725 Washington St",
             e911_city="Yountville", e911_state="CA", e911_zip="94599",
             e911_status="validated", status="active")
    out = S.e911_summary(s)
    assert out["verification"]["state"] == "Verified"
    assert out["verification"]["is_critical"] is False


# ── Support: customer_safe_summary only ──────────────────────────────
def test_support_emits_only_customer_safe():
    session = SupportSession(id=uuid4(), status="escalated", issue_category="device_offline",
                             resolution_summary=None, created_at=NOW)
    diag = SupportDiagnostic(status="warning", customer_safe_summary="Line not responding",
                             internal_summary="LEAKINTERNAL", raw_payload={"x": "LEAKPAYLOAD"},
                             check_type="LEAKCHECK", severity="warning", confidence=0.9)
    user_msg = SupportMessage(role="user", content="No dial tone on Elevator 2", created_at=NOW)
    sys_msg = SupportMessage(role="system", content="LEAKSYSTEMPROMPT", created_at=NOW)
    out = S.support_case_summary(session, messages=[user_msg, sys_msg], diagnostics=[diag])
    blob = _dump(out)
    assert "LEAK" not in blob                       # no internal/raw/system/check leak
    assert "Line not responding" in blob            # customer_safe_summary shown
    assert "No dial tone on Elevator 2" in blob     # user message shown
    assert out["status"] == "In progress (with our team)"
    assert len(out["messages"]) == 1                # system message dropped
