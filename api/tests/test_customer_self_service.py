"""Customer Self-Service (Customer Operations Console) — end-to-end on a real DB.

Runs the real ``/api/customer`` + ``/api/customer-requests`` routers against an
in-memory SQLite database (``tests/_customer_db.py``) so writes, unique keys,
tenant filters and the audit trail are genuinely exercised.  Pins the ownership
boundary: customer-owned fields apply directly (audited old/new);
provisioning / identity / E911 changes become governed requests; system-managed
fields (ICCID / IMEI / verified E911 …) are refused and nothing is applied;
tenant isolation holds; the flags gate everything (feature OFF = unchanged).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.action_audit import ActionAudit
from app.models.customer_self_service import (
    CustomerActivityEvent,
    CustomerManagedField,
    CustomerServiceRequest,
)
from app.models.device import Device
from app.models.portfolio_registry import (
    PortfolioBuilding,
    PortfolioDeviceMapping,
    PortfolioReviewItem,
)
from app.models.site import Site
from app.routers import customer as customer_router
from app.routers import customer_requests as requests_router
from app.services.customer import portfolio_registry_view as prv
from app.services.customer.refs import encode_ref
from tests._customer_db import client_for, make_db, user

RH = "restoration-hardware"
OTHER = "other-co"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
ROUTERS = [(customer_router.router, "/api/customer"),
           (requests_router.router, "/api/customer-requests")]


# ── flags ────────────────────────────────────────────────────────────
@pytest.fixture
def flags(monkeypatch):
    def set_flags(*, self_service="true", ss_tenants=RH, ss_users="", registry="true",
                  api_tenants=f"{RH},{OTHER}"):
        s = "app.config.settings."
        monkeypatch.setattr(s + "FEATURE_CUSTOMER_API", "true")
        monkeypatch.setattr(s + "CUSTOMER_API_TENANT_ALLOWLIST", api_tenants)
        monkeypatch.setattr(s + "FEATURE_CUSTOMER_PREVIEW", "true")
        monkeypatch.setattr(s + "CUSTOMER_PREVIEW_TENANT_ALLOWLIST", f"{RH},{OTHER}")
        monkeypatch.setattr(s + "FEATURE_CUSTOMER_PORTFOLIO_REGISTRY", registry)
        monkeypatch.setattr(s + "CUSTOMER_PORTFOLIO_REGISTRY_TENANT_ALLOWLIST", f"{RH},{OTHER}")
        monkeypatch.setattr(s + "CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS", "false")
        monkeypatch.setattr(s + "CUSTOMER_PORTFOLIO_PREVIEW_PENDING", "false")
        monkeypatch.setattr(s + "FEATURE_CUSTOMER_SELF_SERVICE", self_service)
        monkeypatch.setattr(s + "CUSTOMER_SELF_SERVICE_TENANT_ALLOWLIST", ss_tenants)
        monkeypatch.setattr(s + "CUSTOMER_SELF_SERVICE_USER_ALLOWLIST", ss_users)
    set_flags()
    return set_flags


# ── seed ─────────────────────────────────────────────────────────────
async def seed(Session, *, fused_payload=True):
    async with Session() as db:
        db.add_all([
            Site(site_id="RH-147", tenant_id=RH, site_name="Restoration Hardware #147 Chicago",
                 customer_name="RH", status="active", e911_street="123 Michigan Ave",
                 e911_city="Chicago", e911_state="IL", e911_zip="60601", e911_status="pending",
                 lat=41.88, lng=-87.62),
            Device(device_id="D-147-1", tenant_id=RH, site_id="RH-147", status="active",
                   device_type="communicator", model="StarLink", msisdn="3125550100",
                   iccid="8901000000000000001"),
            PortfolioBuilding(id=1, tenant_id=RH, canonical_name="Chicago Gallery #147",
                              store_number="147", site_type="gallery", status="active",
                              address="123 Michigan Ave", city="Chicago", state="IL",
                              zip="60601", approved=True, approved_by="ops"),
            PortfolioBuilding(id=2, tenant_id=RH, canonical_name="Austin Gallery #149",
                              store_number="149", site_type="gallery", status="active",
                              address="1 Congress Ave", city="Austin", state="TX", zip="78701",
                              approved=True, approved_by="ops"),
            PortfolioBuilding(id=3, tenant_id=OTHER, canonical_name="Other Co HQ",
                              store_number="9", site_type="corporate", status="active",
                              address="9 Elm St", city="Dover", state="DE", zip="19901",
                              approved=True, approved_by="ops"),
            Site(site_id="OT-1", tenant_id=OTHER, site_name="Other Co HQ", customer_name="OT",
                 status="active", e911_street="9 Elm St", e911_city="Dover", e911_state="DE",
                 e911_zip="19901", e911_status="pending"),
        ])
        for bid, kind, value in (
            (1, "napco_radio", "R-1001"), (1, "iccid", "8901000000000000001"),
            (1, "phone", "3125550100"), (1, "true911_device", "RH-147"),
            (1, "zoho_account", "RH Chicago"),
            (2, "imei", "359000000000001"), (2, "iccid", "8901000000000000002"),
            (2, "genesis_msisdn", "5125550149"), (2, "phone", "5125550149"),
        ):
            db.add(PortfolioDeviceMapping(tenant_id=RH, building_id=bid, kind=kind, value=value,
                                          value_normalized=value.replace("-", "").upper(),
                                          source="test", active=True))
        if fused_payload:
            db.add(PortfolioReviewItem(
                tenant_id=RH, review_type="new_building", status="approved",
                signature="new_building:147:-", candidate_name="RH Chicago", store_number="147",
                payload=json.dumps({"devices": [{"kind": "napco_radio", "radio_number": "R-1001",
                                                 "iccid": "8901000000000000001"}]})))
        await db.commit()


def run(scenario, flags_fixture=None):
    async def _go():
        engine, Session = await make_db()
        try:
            await seed(Session)
            state = {"user": user()}
            async with client_for(ROUTERS, Session, state) as c:
                return await scenario(c, Session, state)
        finally:
            await engine.dispose()
    return asyncio.run(_go())


B1 = encode_ref("bldg", 1)
B2 = encode_ref("bldg", 2)
B_OTHER = encode_ref("bldg", 3)


async def _rows(Session, model, *where):
    async with Session() as db:
        return (await db.execute(select(model).where(*where))).scalars().all()


async def _conn_ref(c, loc=B1, service_contains=None):
    ws = (await c.get(f"/api/customer/locations/{loc}/workspace")).json()["data"]
    conns = ws["connections"]
    if service_contains:
        conns = [x for x in conns if service_contains in (x["phone_number"] or "")]
    return conns[0]["connection_ref"], ws


# ══════════════════════════════════════════════════════════════════════
# Customer-owned edits
# ══════════════════════════════════════════════════════════════════════
def test_admin_edits_customer_owned_field_and_it_persists_with_audit(flags):
    async def sc(c, Session, state):
        r = await c.patch(f"/api/customer/locations/{B1}/profile",
                          json={"changes": {"display_name": "Chicago Flagship",
                                            "access_notes": "Loading dock on Erie St"}})
        assert r.status_code == 200, r.text
        assert sorted(r.json()["data"]["applied"]) == ["access_notes", "display_name"]
        ws = (await c.get(f"/api/customer/locations/{B1}/workspace")).json()["data"]
        assert ws["location"]["display_name"] == "Chicago Flagship"
        assert ws["profile"]["access_notes"] == "Loading dock on Erie St"
        ev = await _rows(Session, CustomerActivityEvent, CustomerActivityEvent.field == "display_name")
        assert len(ev) == 1 and json.loads(ev[0].new_value) == "Chicago Flagship"
        assert ev[0].old_value is None and ev[0].actor_email == "judy@rh.example"
        assert ev[0].origin == "customer_portal" and ev[0].location_key == "bldg:1"
        audits = await _rows(Session, ActionAudit, ActionAudit.action_type == "customer_self_service")
        assert len(audits) == 2
        # a second edit records the OLD value
        await c.patch(f"/api/customer/locations/{B1}/profile",
                      json={"changes": {"display_name": "Chicago Gallery"}})
        ev = await _rows(Session, CustomerActivityEvent, CustomerActivityEvent.field == "display_name")
        assert json.loads(ev[-1].old_value) == "Chicago Flagship"
    run(sc)


def test_registry_building_remains_canonical_identity(flags):
    async def sc(c, Session, state):
        await c.patch(f"/api/customer/locations/{B1}/profile",
                      json={"changes": {"display_name": "Our Chicago Store"}})
        b = (await _rows(Session, PortfolioBuilding, PortfolioBuilding.id == 1))[0]
        assert b.canonical_name == "Chicago Gallery #147"          # registry untouched
        ws = (await c.get(f"/api/customer/locations/{B1}/workspace")).json()["data"]
        assert ws["location"]["canonical_name"] == "Chicago Gallery #147"
        assert ws["location"]["display_name"] == "Our Chicago Store"
        assert ws["location"]["location_ref"] == B1                # identity ref unchanged
    run(sc)


def test_viewer_cannot_edit(flags):
    async def sc(c, Session, state):
        for role in ("CUSTOMER_VIEWER", "CUSTOMER_READONLY", "CUSTOMER_BILLING"):
            state["user"] = user(role=role)
            r = await c.patch(f"/api/customer/locations/{B1}/profile",
                              json={"changes": {"display_name": "x"}})
            assert r.status_code == 403, role
            r = await c.put(f"/api/customer/locations/{B1}/contacts",
                            json={"contacts": {"facility": {"name": "x", "phone": "5551234567"}}})
            assert r.status_code == 403, role
            r = await c.post(f"/api/customer/locations/{B1}/requests",
                             json={"request_type": "support_request", "notes": "help"})
            assert r.status_code == 403, role
            # read-only roles can still SEE the workspace
            assert (await c.get(f"/api/customer/locations/{B1}/workspace")).status_code == 200
        assert await _rows(Session, CustomerManagedField) == []
    run(sc)


def test_manager_gets_only_the_operational_subset(flags):
    async def sc(c, Session, state):
        state["user"] = user(role="CUSTOMER_MANAGER", email="mgr@rh.example", name="Mo")
        ok = await c.put(f"/api/customer/locations/{B1}/contacts",
                         json={"contacts": {"facility": {"name": "Pat", "phone": "3125550111"}}})
        assert ok.status_code == 200
        req = await c.post(f"/api/customer/locations/{B1}/requests",
                           json={"request_type": "support_request", "notes": "Panel beeping"})
        assert req.status_code == 200
        assert (await c.patch(f"/api/customer/locations/{B1}/profile",
                              json={"changes": {"display_name": "x"}})).status_code == 403
        assert (await c.post(f"/api/customer/locations/{B1}/e911/verification",
                             json={"attest": True, "address_confirmed": True,
                                   "building_confirmed": True})).status_code == 403
        caps = (await c.get("/api/customer/self-service/capabilities")).json()["data"]
        assert caps["can_manage_contacts"] and caps["can_submit_requests"]
        assert not caps["can_manage_location"] and not caps["can_attest_e911"]
    run(sc)


def test_cross_tenant_edit_rejected(flags):
    async def sc(c, Session, state):
        # RH admin aims at another tenant's building (a validly-signed ref)
        r = await c.patch(f"/api/customer/locations/{B_OTHER}/profile",
                          json={"changes": {"display_name": "hijack"}})
        assert r.status_code == 404
        r = await c.post(f"/api/customer/locations/{B_OTHER}/requests",
                         json={"request_type": "remove_service", "notes": "x"})
        assert r.status_code == 404
        # forged ref
        assert (await c.patch("/api/customer/locations/bldg_Zm9yZ2Vk.xxxx/profile",
                              json={"changes": {"display_name": "x"}})).status_code == 404
        # another tenant's user cannot read or touch RH requests
        rq = (await c.post(f"/api/customer/locations/{B1}/requests",
                           json={"request_type": "support_request", "notes": "x"})).json()["data"]
        state["user"] = user(tenant=OTHER, email="o@other.example")
        # (OTHER is not self-service allowlisted -> whole surface 404s)
        assert (await c.get(f"/api/customer/requests/{rq['request_ref']}")).status_code == 404
        assert await _rows(Session, CustomerManagedField) == []
    run(sc)


def test_connection_ref_is_bound_to_its_location(flags):
    async def sc(c, Session, state):
        conn_ref, _ws = await _conn_ref(c, B1)
        # the same signed connection ref used against a different location -> 404
        r = await c.patch(f"/api/customer/locations/{B2}/connections/{conn_ref}",
                          json={"changes": {"friendly_name": "x"}})
        assert r.status_code == 404
        r = await c.patch(f"/api/customer/locations/{B1}/connections/conn_bad.sig",
                          json={"changes": {"friendly_name": "x"}})
        assert r.status_code == 404
    run(sc)


# ══════════════════════════════════════════════════════════════════════
# The boundary: system-managed refused, provisioning-impacting -> request
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("forbidden", ["iccid", "imei", "sim_status", "carrier_account",
                                       "sip_password", "e911_status", "verified", "device_id"])
def test_system_managed_fields_refused_and_nothing_applied(flags, forbidden):
    async def sc(c, Session, state):
        conn_ref, _ = await _conn_ref(c, B1)
        r = await c.patch(f"/api/customer/locations/{B1}/connections/{conn_ref}",
                          json={"changes": {"friendly_name": "Lobby FACP", forbidden: "X"}})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "system_managed_field"
        r = await c.patch(f"/api/customer/locations/{B1}/profile",
                          json={"changes": {"display_name": "ok", forbidden: "X"}})
        assert r.status_code == 403
        # atomic refusal: the allowed half of the payload was NOT applied either
        assert await _rows(Session, CustomerManagedField) == []
        assert await _rows(Session, CustomerServiceRequest) == []
        # and the system records are untouched
        d = (await _rows(Session, Device, Device.device_id == "D-147-1"))[0]
        assert d.iccid == "8901000000000000001" and d.imei is None
    run(sc)


def test_customer_cannot_alter_iccid_or_imei_via_a_request_payload(flags):
    async def sc(c, Session, state):
        r = await c.post(f"/api/customer/locations/{B1}/requests",
                         json={"request_type": "replace_device", "notes": "swap",
                               "requested_changes": {"iccid": "8901999"}})
        assert r.status_code == 403
        r = await c.post(f"/api/customer/locations/{B1}/requests",
                         json={"request_type": "replace_device", "notes": "swap",
                               "requested_changes": {"IMEI": "35999"}})
        assert r.status_code == 403
        assert await _rows(Session, CustomerServiceRequest) == []
    run(sc)


def test_provisioning_sensitive_change_creates_request_not_a_write(flags):
    async def sc(c, Session, state):
        conn_ref, _ = await _conn_ref(c, B1)
        r = await c.patch(f"/api/customer/locations/{B1}/connections/{conn_ref}",
                          json={"changes": {"friendly_name": "Fire Alarm Line 1",
                                            "purpose": "fire_alarm",
                                            "phone_number": "3125559999"}})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert sorted(data["applied"]) == ["friendly_name", "purpose"]
        assert data["requested"] == ["phone_number"]
        assert data["requests"][0]["request_type"] == "change_number"
        assert data["requests"][0]["status"] == "submitted"
        # the carrier/device number is untouched
        d = (await _rows(Session, Device, Device.device_id == "D-147-1"))[0]
        assert d.msisdn == "3125550100"
        # identity fields on the location also become a request, never a write
        r = await c.patch(f"/api/customer/locations/{B1}/profile",
                          json={"changes": {"address": "999 Wrong St", "store_number": "148"}})
        assert r.status_code == 200
        assert r.json()["data"]["applied"] == []
        assert r.json()["data"]["request"]["request_type"] == "location_correction"
        b = (await _rows(Session, PortfolioBuilding, PortfolioBuilding.id == 1))[0]
        assert b.address == "123 Michigan Ave" and b.store_number == "147"
    run(sc)


@pytest.mark.parametrize("rtype", ["add_service", "remove_service", "move_service",
                                   "replace_device", "change_service_type", "support_request"])
def test_service_requests_are_created_and_visible(flags, rtype):
    async def sc(c, Session, state):
        r = await c.post(f"/api/customer/locations/{B1}/requests",
                         json={"request_type": rtype, "notes": f"Please {rtype}",
                               "requested_changes": {"service_purpose": "elevator"}})
        assert r.status_code == 200, r.text
        req = r.json()["data"]
        assert req["request_type"] == rtype and req["status"] == "submitted" and req["open"]
        rows = await _rows(Session, CustomerServiceRequest)
        assert len(rows) == 1 and rows[0].tenant_id == RH and rows[0].location_key == "bldg:1"
        listed = (await c.get("/api/customer/requests?open=true")).json()["data"]["requests"]
        assert [x["request_ref"] for x in listed] == [req["request_ref"]]
        ev = await _rows(Session, CustomerActivityEvent,
                         CustomerActivityEvent.event_type == "request_submitted")
        assert len(ev) == 1 and ev[0].request_ref == req["request_ref"]
    run(sc)


def test_request_validation(flags):
    async def sc(c, Session, state):
        bad = await c.post(f"/api/customer/locations/{B1}/requests",
                           json={"request_type": "reprovision_everything", "notes": "x"})
        assert bad.status_code == 422
        empty = await c.post(f"/api/customer/locations/{B1}/requests",
                             json={"request_type": "add_service"})
        assert empty.status_code == 422
        e911 = await c.post(f"/api/customer/locations/{B1}/requests",
                            json={"request_type": "e911_verification", "notes": "x"})
        assert e911.status_code == 422            # must go through Verify E911
    run(sc)


# ══════════════════════════════════════════════════════════════════════
# Contacts + activity
# ══════════════════════════════════════════════════════════════════════
def test_contact_update_persists_and_audits(flags):
    async def sc(c, Session, state):
        body = {"contacts": {"emergency": {"name": "Sam Lee", "phone": "(312) 555-0199",
                                           "email": "sam@rh.example", "title": "GM"}}}
        r = await c.put(f"/api/customer/locations/{B1}/contacts", json=body)
        assert r.status_code == 200 and r.json()["data"]["applied"] == ["emergency"]
        ws = (await c.get(f"/api/customer/locations/{B1}/workspace")).json()["data"]
        assert ws["contacts"]["contacts"]["emergency"]["name"] == "Sam Lee"
        assert ws["contacts"]["missing"] is False
        ev = await _rows(Session, CustomerActivityEvent,
                         CustomerActivityEvent.field == "contact.emergency")
        assert len(ev) == 1 and ev[0].summary == "Updated emergency contact"
        # invalid contact rejected; unreachable contact rejected
        bad = await c.put(f"/api/customer/locations/{B1}/contacts",
                          json={"contacts": {"emergency": {"name": "x", "email": "nope"}}})
        assert bad.status_code == 422
        bad = await c.put(f"/api/customer/locations/{B1}/contacts",
                          json={"contacts": {"emergency": {"name": "no way to reach"}}})
        assert bad.status_code == 422
        # clearing is audited as a removal with the old value
        await c.put(f"/api/customer/locations/{B1}/contacts", json={"contacts": {"emergency": None}})
        ev = await _rows(Session, CustomerActivityEvent,
                         CustomerActivityEvent.field == "contact.emergency")
        assert ev[-1].summary == "Removed emergency contact"
        assert json.loads(ev[-1].old_value)["name"] == "Sam Lee"
    run(sc)


def test_activity_history_records_mutations(flags):
    async def sc(c, Session, state):
        await c.put(f"/api/customer/locations/{B1}/contacts",
                    json={"contacts": {"facility": {"name": "Pat", "phone": "3125550111"}}})
        await c.post(f"/api/customer/locations/{B1}/requests",
                     json={"request_type": "add_service", "notes": "New elevator"})
        act = (await c.get(f"/api/customer/locations/{B1}/activity")).json()["data"]["activity"]
        summaries = [a["summary"] for a in act]
        assert "Add service requested" in summaries and "Updated facility contact" in summaries
        assert all(a["by"] == "Judy" for a in act)
        # another location's activity is separate
        other = (await c.get(f"/api/customer/locations/{B2}/activity")).json()["data"]["activity"]
        assert other == []
    run(sc)


# ══════════════════════════════════════════════════════════════════════
# E911 self-service
# ══════════════════════════════════════════════════════════════════════
def test_e911_submission_creates_pending_verification_never_verified(flags):
    async def sc(c, Session, state):
        before = (await c.get(f"/api/customer/locations/{B1}/e911/verification")).json()["data"]
        assert before["state"] == "customer_confirmation_required"
        assert before["dispatch_address"].startswith("123 Michigan Ave")
        assert before["verified"] is False
        r = await c.post(f"/api/customer/locations/{B1}/e911/verification",
                         json={"number_confirmed": True, "address_confirmed": True,
                               "building_confirmed": True,
                               "attest": True, "note": "Checked on site"})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["request"]["request_type"] == "e911_verification"
        assert data["request"]["status"] == "submitted"
        assert data["e911"]["state"] == "customer_submitted" and data["e911"]["verified"] is False
        prov = data["e911"]["provenance"]
        assert prov["verification_method"] == "customer_attestation" and prov["attested_by"] == "Judy"
        # the official record is untouched and NOT verified
        site = (await _rows(Session, Site, Site.site_id == "RH-147"))[0]
        assert site.e911_status == "pending"
        # it reached the EXISTING internal E911 review queue
        q = await _rows(Session, ActionAudit, ActionAudit.action_type == "e911_customer_confirm")
        assert len(q) == 1 and q[0].site_id == "RH-147"
        req = (await _rows(Session, CustomerServiceRequest))[0]
        assert json.loads(req.requested_changes)["e911_review_id"]
        # the server-side snapshot, not client content, is what was attested
        snap = json.loads(req.requested_changes)["server_snapshot"]
        assert snap["dispatch_address"].startswith("123 Michigan Ave")
    run(sc)


def test_e911_attestation_required_and_corrections_go_to_review(flags):
    async def sc(c, Session, state):
        no = await c.post(f"/api/customer/locations/{B1}/e911/verification",
                          json={"address_confirmed": True, "building_confirmed": True})
        assert no.status_code == 422 and no.json()["detail"]["code"] == "attestation_required"
        r = await c.post(f"/api/customer/locations/{B1}/e911/verification",
                         json={"building_confirmed": True, "attest": True,
                               "corrected_address": "125 Michigan Ave", "suite": "B"})
        assert r.status_code == 200
        assert r.json()["data"]["e911"]["state"] == "requires_review"
        corr = await _rows(Session, ActionAudit, ActionAudit.action_type == "e911_correction_request")
        assert len(corr) == 1
        site = (await _rows(Session, Site, Site.site_id == "RH-147"))[0]
        assert site.e911_street == "123 Michigan Ave" and site.e911_status == "pending"
    run(sc)


def test_customer_cannot_set_e911_verified_directly(flags):
    async def sc(c, Session, state):
        for field in ("e911_status", "e911_verified", "verified", "verification_status"):
            r = await c.patch(f"/api/customer/locations/{B1}/profile",
                              json={"changes": {field: "verified"}})
            assert r.status_code == 403
        site = (await _rows(Session, Site, Site.site_id == "RH-147"))[0]
        assert site.e911_status == "pending"
    run(sc)


# ══════════════════════════════════════════════════════════════════════
# Operations queue (internal) + customer lifecycle actions
# ══════════════════════════════════════════════════════════════════════
def test_operations_queue_is_internal_only_and_transitions_are_audited(flags):
    async def sc(c, Session, state):
        rq = (await c.post(f"/api/customer/locations/{B1}/e911/verification",
                           json={"address_confirmed": True, "building_confirmed": True,
                                 "attest": True})).json()["data"]["request"]
        # a customer role cannot reach the internal queue
        assert (await c.get("/api/customer-requests")).status_code == 403
        state["user"] = user(role="Admin", email="ops@ops.example", name="Opal")
        q = (await c.get("/api/customer-requests")).json()
        assert q["count"] == 1 and q["requests"][0]["request_ref"] == rq["request_ref"]
        bad = await c.post(f"/api/customer-requests/{rq['request_ref']}/transition",
                           json={"to_status": "cancelled"})
        assert bad.status_code == 409
        for to in ("under_review", "in_progress", "completed"):
            r = await c.post(f"/api/customer-requests/{rq['request_ref']}/transition",
                             json={"to_status": to, "notes": "done"})
            assert r.status_code == 200, r.text
        # completing the E911 request does NOT verify E911
        site = (await _rows(Session, Site, Site.site_id == "RH-147"))[0]
        assert site.e911_status == "pending"
        state["user"] = user()
        e = (await c.get(f"/api/customer/locations/{B1}/e911/verification")).json()["data"]
        assert e["state"] == "verification_pending" and e["verified"] is False
        act = (await c.get(f"/api/customer/locations/{B1}/activity")).json()["data"]["activity"]
        ops = [a for a in act if a["origin"] == "operations"]
        assert len(ops) == 3 and all(a["by"] == "Operations team" for a in ops)
        assert "ops@ops.example" not in json.dumps(act)          # no staff identities
    run(sc)


def test_customer_cancel_and_respond(flags):
    async def sc(c, Session, state):
        rq = (await c.post(f"/api/customer/locations/{B1}/requests",
                           json={"request_type": "move_service", "notes": "Move to 2F"})).json()["data"]
        state["user"] = user(role="Admin", email="ops@ops.example")
        await c.post(f"/api/customer-requests/{rq['request_ref']}/transition",
                     json={"to_status": "waiting_customer", "notes": "Which room?"})
        state["user"] = user()
        ac = (await c.get("/api/customer/action-center")).json()["data"]
        assert [x["request_ref"] for x in ac["awaiting_your_response"]] == [rq["request_ref"]]
        r = await c.post(f"/api/customer/requests/{rq['request_ref']}/respond",
                         json={"notes": "Room 210"})
        assert r.status_code == 200 and r.json()["data"]["status"] == "submitted"
        r = await c.post(f"/api/customer/requests/{rq['request_ref']}/cancel", json={})
        assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled"
        again = await c.post(f"/api/customer/requests/{rq['request_ref']}/cancel", json={})
        assert again.status_code == 409
    run(sc)


# ══════════════════════════════════════════════════════════════════════
# Action Center + connections + Devices KPI
# ══════════════════════════════════════════════════════════════════════
def test_action_center_surfaces_what_the_customer_must_do(flags):
    async def sc(c, Session, state):
        ac = (await c.get("/api/customer/action-center")).json()["data"]
        e911 = {x["location"] for x in ac["e911_verification_required"]}
        missing = {x["location"] for x in ac["missing_contact_information"]}
        assert len(e911) == 2 and len(missing) == 2
        assert ac["counts"]["locations"] == 2                      # RH only, never OTHER
        await c.put(f"/api/customer/locations/{B1}/contacts",
                    json={"contacts": {"facility": {"name": "Pat", "phone": "3125550111"}}})
        await c.post(f"/api/customer/locations/{B1}/e911/verification",
                     json={"address_confirmed": True, "building_confirmed": True, "attest": True})
        await c.post(f"/api/customer/locations/{B2}/requests",
                     json={"request_type": "support_request", "notes": "Line is dead"})
        ac = (await c.get("/api/customer/action-center")).json()["data"]
        assert len(ac["e911_verification_required"]) == 1
        assert len(ac["missing_contact_information"]) == 1
        assert len(ac["open_problems"]) == 1 and ac["open_problems"][0]["location_ref"] == B2
        assert ac["recently_updated"]
    run(sc)


def test_connections_are_customer_language_without_carrier_internals(flags):
    async def sc(c, Session, state):
        ws = (await c.get(f"/api/customer/locations/{B2}/workspace")).json()["data"]
        dump = json.dumps(ws).lower()
        for leak in ("iccid", "imei", "8901000000000000002", "359000000000001", "napco",
                     "genesis", "zoho", "sim", "msisdn"):
            assert leak not in dump, leak
        # a registry-known number with no monitored service is shown honestly (not green)
        assert ws["connections"][0]["phone_number"] == "(512) 555-0149"
        assert ws["connections"][0]["status"]["status"] == "Unknown"
        assert ws["location"]["device_count"] == 1                  # the IMEI-anchored unit
    run(sc)


def test_device_kpi_counts_physical_devices_across_identifiers(flags):
    async def sc(c, Session, state):
        from app.services.customer import portfolio_registry_view as p
        async with Session() as db:
            recs = await p.load_customer_buildings(db, RH, NOW)
        by_id = {r["id"]: r for r in recs}
        # Chicago: Napco radio + its SIM + its number + the True911 device carrying
        # the same SIM/number = ONE physical device
        assert by_id[1]["physical_device_count"] == 1
        # Austin: IMEI + ICCID + MSISDN + phone = ONE physical device (no True911 site)
        assert by_id[2]["physical_device_count"] == 1
        s = p.summary(recs, "RH", NOW)
        assert s["devices"] == 2 and s["total_devices"] == 2
        assert s["total_phone_numbers"] == 2
        assert "critical_sites" in s and "sites_requiring_attention" in s
    run(sc)


# ══════════════════════════════════════════════════════════════════════
# Flags, allowlists, legacy compatibility
# ══════════════════════════════════════════════════════════════════════
def test_feature_off_preserves_current_behavior(flags):
    flags(self_service="false")

    async def sc(c, Session, state):
        for method, path, body in (
            ("get", "/api/customer/self-service/capabilities", None),
            ("get", "/api/customer/action-center", None),
            ("get", f"/api/customer/locations/{B1}/workspace", None),
            ("patch", f"/api/customer/locations/{B1}/profile", {"changes": {"display_name": "x"}}),
            ("post", f"/api/customer/locations/{B1}/requests",
             {"request_type": "support_request", "notes": "x"}),
        ):
            r = await (getattr(c, method)(path, json=body) if body else getattr(c, method)(path))
            assert r.status_code == 404, path
        state["user"] = user(role="Admin", email="ops@ops.example")
        assert (await c.get("/api/customer-requests")).status_code == 404
        state["user"] = user()
        # the existing read-only customer surface is unaffected
        assert (await c.get("/api/customer/dashboard")).status_code == 200
        assert (await c.get(f"/api/customer/locations/{B1}")).status_code == 200
        assert await _rows(Session, CustomerManagedField) == []
    run(sc)


def test_allowlist_enables_only_rh_test_user(flags):
    flags(ss_users="rh-test@rh.example")

    async def sc(c, Session, state):
        # Judy (same tenant, not on the user allowlist) sees nothing yet
        assert (await c.get("/api/customer/self-service/capabilities")).status_code == 404
        state["user"] = user(email="RH-Test@rh.example", name="RH Test")
        caps = await c.get("/api/customer/self-service/capabilities")
        assert caps.status_code == 200 and caps.json()["data"]["enabled"] is True
        # a different tenant is never enabled by an RH allowlist
        state["user"] = user(tenant=OTHER, email="rh-test@rh.example")
        assert (await c.get("/api/customer/self-service/capabilities")).status_code == 404
    run(sc)


def test_legacy_site_mode_compatibility(flags):
    flags(registry="false")

    async def sc(c, Session, state):
        async with Session() as db:
            site = (await db.execute(select(Site).where(Site.site_id == "RH-147"))).scalar_one()
        loc = encode_ref("loc", site.id)
        assert (await c.get(f"/api/customer/locations/{B1}/workspace")).status_code == 404
        ws = await c.get(f"/api/customer/locations/{loc}/workspace")
        assert ws.status_code == 200, ws.text
        assert ws.json()["data"]["location"]["canonical_name"] == "Restoration Hardware #147 Chicago"
        r = await c.patch(f"/api/customer/locations/{loc}/profile",
                          json={"changes": {"location_notes": "Key at front desk"}})
        assert r.status_code == 200
        f = (await _rows(Session, CustomerManagedField))[0]
        assert f.location_key == "site:RH-147" and f.building_id is None
        e = await c.post(f"/api/customer/locations/{loc}/e911/verification",
                         json={"address_confirmed": True, "building_confirmed": True,
                               "attest": True})
        assert e.status_code == 200
        assert e.json()["data"]["e911"]["state"] == "customer_submitted"
    run(sc)


def test_registry_rows_untouched_by_every_customer_mutation(flags):
    async def sc(c, Session, state):
        before = [(m.kind, m.value, m.building_id) for m in await _rows(Session, PortfolioDeviceMapping)]
        conn_ref, _ = await _conn_ref(c, B1)
        await c.patch(f"/api/customer/locations/{B1}/connections/{conn_ref}",
                      json={"changes": {"friendly_name": "Elevator 1", "purpose": "elevator",
                                        "service_type": "fire_alarm"}})
        await c.post(f"/api/customer/locations/{B1}/requests",
                     json={"request_type": "remove_service", "notes": "Closing the store"})
        after = [(m.kind, m.value, m.building_id) for m in await _rows(Session, PortfolioDeviceMapping)]
        assert before == after
        assert prv  # module import sanity (registry view unchanged)
    run(sc)
