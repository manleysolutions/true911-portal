"""Tests for Ops Center Phase 1.5 — operational-intelligence foundations.

Foundations only: enums/severity mapping, the escalation-queue builder, and
the read-only CustomerHealthSnapshot / VendorContext service stubs.  Uses the
same queued in-memory AsyncSession substitute pattern as test_ops_center.py.
Nothing here enables FEATURE_OPS_CENTER or exercises a route.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.ops_center_intelligence import (
    OpsEscalationQueue,
    OpsKnowledgeArticle,
    OpsPlaybook,
    OpsResolutionPattern,
)
from app.services.ops_center.intelligence import (
    EscalationQueueStatus,
    IncidentSeverity,
    KnowledgeArticleStatus,
    PlaybookStatus,
    ResolutionPatternStatus,
    priority_for_severity,
    severity_for_issue,
)
from app.services.ops_center.intelligence import escalation_queue as eq
from app.services.ops_center.intelligence import health_snapshot as hs
from app.services.ops_center.intelligence import vendor_context as vc


# ── queued in-memory async session ──────────────────────────────────

class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeDB:
    def __init__(self, results=None):
        self._queue = list(results or [])
        self.added = []

    async def execute(self, stmt, *a, **k):
        rows = self._queue.pop(0) if self._queue else []
        return _Result(rows)

    def add(self, obj):
        self.added.append(obj)

    def added_of(self, cls):
        return [o for o in self.added if isinstance(o, cls)]


def _device(**kw):
    base = dict(
        device_id="dev-1", tenant_id="rh", status="active",
        last_heartbeat=datetime.now(timezone.utc), iccid="8901240200000000000",
        msisdn="8563081391", model="NAPCO StarLink", manufacturer="NAPCO",
        device_type="cellular", identifier_type="cellular", carrier="T-Mobile",
        firmware_version="1.2.3", starlink_id="SL-123", last_network_event=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ════════════════════════════════════════════════════════════════════
# Enums + severity mapping
# ════════════════════════════════════════════════════════════════════

def test_incident_severity_values_align_with_existing_vocab():
    assert IncidentSeverity.CRITICAL.value == "critical"
    assert IncidentSeverity.INFO.value == "info"
    # str-enum members compare equal to their string value
    assert IncidentSeverity.HIGH == "high"


def test_status_enums_present():
    assert EscalationQueueStatus.QUEUED.value == "queued"
    assert KnowledgeArticleStatus.PUBLISHED.value == "published"
    assert PlaybookStatus.ACTIVE.value == "active"
    assert ResolutionPatternStatus.CONFIRMED.value == "confirmed"


@pytest.mark.parametrize(
    "category,expected",
    [
        ("area_of_refuge_issue", "critical"),
        ("fire_panel_issue", "critical"),
        ("no_dial_tone", "high"),
        ("device_offline", "high"),
        ("gate_phone_issue", "moderate"),
        ("billing_question", "low"),
        ("general_support", "info"),
        ("totally_unknown_cat", "moderate"),
        (None, "moderate"),
    ],
)
def test_severity_for_issue_mapping(category, expected):
    assert severity_for_issue(category).value == expected


def test_emergency_always_critical():
    assert severity_for_issue("billing_question", is_emergency=True) == IncidentSeverity.CRITICAL


def test_priority_for_severity_ordering():
    assert priority_for_severity(IncidentSeverity.CRITICAL) == 1
    assert priority_for_severity("info") == 5
    assert priority_for_severity("nonsense") == 3  # defaults to moderate rank


# ════════════════════════════════════════════════════════════════════
# Escalation-queue builder
# ════════════════════════════════════════════════════════════════════

def test_build_escalation_entry_derives_severity_and_priority():
    session = SimpleNamespace(
        id=uuid4(), session_ref="OPS-AAAA1111", matched_tenant_id="rh",
        issue_category="no_dial_tone", is_emergency=False, issue_summary="No dial tone",
        handoff_number=None, incident_ref=None, matched_site_id="S1", matched_device_id="dev-1",
    )
    entry = eq.build_escalation_entry(session)
    assert isinstance(entry, OpsEscalationQueue)
    assert entry.severity == "high" and entry.priority == 2
    assert entry.status == "queued" and entry.tenant_id == "rh"
    assert entry.session_ref == "OPS-AAAA1111" and entry.device_id == "dev-1"


def test_build_escalation_entry_emergency_is_critical_p1():
    session = SimpleNamespace(
        id=uuid4(), session_ref="OPS-BBBB2222", matched_tenant_id="rh",
        issue_category="general_support", is_emergency=True, issue_summary=None,
        handoff_number="+15551112222", incident_ref="INC-OPS-1", matched_site_id=None, matched_device_id=None,
    )
    entry = eq.build_escalation_entry(session)
    assert entry.severity == "critical" and entry.priority == 1
    assert entry.is_emergency is True and entry.incident_ref == "INC-OPS-1"


@pytest.mark.asyncio
async def test_enqueue_escalation_adds_row():
    session = SimpleNamespace(
        id=uuid4(), session_ref="OPS-CCCC3333", matched_tenant_id="rh",
        issue_category="gate_phone_issue", is_emergency=False, issue_summary="x",
        handoff_number=None, incident_ref=None, matched_site_id=None, matched_device_id=None,
    )
    db = FakeDB()
    entry = await eq.enqueue_escalation(db, session)
    assert db.added_of(OpsEscalationQueue) == [entry]
    assert entry.severity == "moderate" and entry.priority == 3


# ════════════════════════════════════════════════════════════════════
# CustomerHealthSnapshot (read-only stub)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_snapshot_unknown_without_devices():
    db = FakeDB(results=[[]])
    snap = await hs.build_customer_health_snapshot(db, "rh")
    assert snap.label == "unknown" and snap.total_devices == 0
    assert snap.degraded is True


@pytest.mark.asyncio
async def test_health_snapshot_protected_when_all_fresh():
    now = datetime.now(timezone.utc)
    devices = [_device(device_id=f"d{i}", last_heartbeat=now) for i in range(3)]
    db = FakeDB(results=[devices])
    snap = await hs.build_customer_health_snapshot(db, "rh", now=now)
    assert snap.total_devices == 3 and snap.active_devices == 3
    assert snap.stale_devices == 0 and snap.label == "protected"


@pytest.mark.asyncio
async def test_health_snapshot_critical_when_majority_stale():
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=3)
    devices = [
        _device(device_id="d1", last_heartbeat=old),
        _device(device_id="d2", last_heartbeat=old),
        _device(device_id="d3", last_heartbeat=now),
    ]
    db = FakeDB(results=[devices])
    snap = await hs.build_customer_health_snapshot(db, "rh", now=now)
    assert snap.stale_devices == 2 and snap.label == "critical"


@pytest.mark.asyncio
async def test_health_snapshot_ignores_inactive_devices():
    now = datetime.now(timezone.utc)
    devices = [
        _device(device_id="d1", status="decommissioned", last_heartbeat=None),
        _device(device_id="d2", status="active", last_heartbeat=now),
    ]
    db = FakeDB(results=[devices])
    snap = await hs.build_customer_health_snapshot(db, "rh", now=now)
    assert snap.inactive_devices == 1 and snap.active_devices == 1
    assert snap.label == "protected"  # only the monitored device counts


# ════════════════════════════════════════════════════════════════════
# VendorContext (service-output stub)
# ════════════════════════════════════════════════════════════════════

def test_context_from_device_normalizes_fields():
    ctx = vc.context_from_device(_device())
    assert ctx.available is True
    assert ctx.carrier == "T-Mobile" and ctx.vendor == "napco"
    assert ctx.transport == "cellular" and ctx.iccid == "8901240200000000000"


@pytest.mark.asyncio
async def test_build_vendor_context_degrades_without_device_id():
    db = FakeDB()
    ctx = await vc.build_vendor_context(db, device_id=None, tenant_id="rh")
    assert ctx.available is False and ctx.notes


@pytest.mark.asyncio
async def test_build_vendor_context_degrades_when_not_found():
    db = FakeDB(results=[[]])  # device lookup returns nothing
    ctx = await vc.build_vendor_context(db, device_id="missing", tenant_id="rh")
    assert ctx.available is False and ctx.device_id == "missing"


@pytest.mark.asyncio
async def test_build_vendor_context_returns_context_for_known_device():
    db = FakeDB(results=[[_device()]])
    ctx = await vc.build_vendor_context(db, device_id="dev-1", tenant_id="rh")
    assert ctx.available is True and ctx.vendor == "napco" and ctx.carrier == "T-Mobile"


# ════════════════════════════════════════════════════════════════════
# Model importability (schema scaffolding present)
# ════════════════════════════════════════════════════════════════════

def test_intelligence_models_have_expected_tables():
    assert OpsEscalationQueue.__tablename__ == "ops_escalation_queue"
    assert OpsKnowledgeArticle.__tablename__ == "ops_knowledge_articles"
    assert OpsPlaybook.__tablename__ == "ops_playbooks"
    assert OpsResolutionPattern.__tablename__ == "ops_resolution_patterns"
