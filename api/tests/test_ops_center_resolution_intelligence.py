"""Tests for Ops Center Phase 1.6 — Resolution Intelligence (foundations).

Covers the static knowledge catalog's structural integrity, the deterministic
rules-based matcher and recommendation engine, the diagnostic/resolution
accessors, and the idempotent DB seeder.  Everything here is pure Python or
uses the queued in-memory AsyncSession substitute from the Phase-1.5 tests —
no database, no LLM, no route, and nothing enables ``FEATURE_OPS_CENTER``.
"""

from __future__ import annotations

import pytest

from app.models.ops_center_resolution import (
    OpsDiagnosticWorkflow,
    OpsKnownIssue,
    OpsResolutionOutcome,
    OpsResolutionWorkflow,
)
from app.services.ops_center.resolution_intelligence import (
    EscalationQueue,
    OutcomeType,
    find_matching_issues,
    get_known_issue,
    recommend,
)
from app.services.ops_center.resolution_intelligence.catalog import (
    RESOLUTION_CATALOG,
    DiagnosticSpec,
    KnownIssueSpec,
    ResolutionSpec,
)
from app.services.ops_center.resolution_intelligence.constants import (
    ESCALATION_QUEUES,
    OUTCOME_TYPES,
    IncidentSeverity,
)
from app.services.ops_center.resolution_intelligence.diagnostics import (
    diagnostic_for_issue,
    diagnostic_to_dict,
)
from app.services.ops_center.resolution_intelligence.resolutions import (
    resolution_for_issue,
    resolution_to_dict,
)
from app.services.ops_center.resolution_intelligence.seed import (
    seed_resolution_intelligence,
)


# ── queued in-memory async session (mirrors test_ops_center_intelligence) ──

class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return _Scalars(self._rows)


class FakeDB:
    def __init__(self, results=None):
        self._queue = list(results or [])
        self.added = []
        self.commits = 0

    async def execute(self, stmt, *a, **k):
        rows = self._queue.pop(0) if self._queue else []
        return _Result(rows)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    def added_of(self, cls):
        return [o for o in self.added if isinstance(o, cls)]


def _spec(code="synthetic_issue", **kw) -> KnownIssueSpec:
    """A minimal synthetic catalog entry, for behaviour the real catalog
    happens not to exercise."""
    base = dict(
        code=code,
        title="Synthetic issue",
        category="synthetic_domain",
        severity=IncidentSeverity.MODERATE.value,
        description="A synthetic issue used only by tests.",
        symptoms=["something is wrong"],
        probable_causes=["a synthetic cause"],
        escalation_queue=EscalationQueue.NOC.value,
        diagnostic=DiagnosticSpec(
            code=f"diag_{code}",
            title="Synthetic diagnostic",
            ordered_steps=[{"order": 1, "action": "look at it"}],
            expected_results=["it looks fine"],
            failure_paths=[{"when": "it does not", "do": "escalate", "escalate_to": "NOC"}],
            escalation_queue=EscalationQueue.NOC.value,
        ),
        resolution=ResolutionSpec(
            code=f"res_{code}",
            title="Synthetic resolution",
            resolution_steps=[{"order": 1, "action": "fix it"}],
            estimated_time_minutes=5,
            escalation_trigger="it is still broken",
            success_criteria=["it works"],
        ),
    )
    base.update(kw)
    return KnownIssueSpec(**base)


# ════════════════════════════════════════════════════════════════════
# Catalog integrity
# ════════════════════════════════════════════════════════════════════

def test_catalog_is_non_empty_and_codes_are_unique():
    codes = [spec.code for spec in RESOLUTION_CATALOG]
    assert len(codes) >= 20
    assert len(codes) == len(set(codes)), "duplicate known-issue code in the catalog"


def test_workflow_codes_are_unique_across_the_catalog():
    diag_codes = [s.diagnostic.code for s in RESOLUTION_CATALOG if s.diagnostic]
    res_codes = [s.resolution.code for s in RESOLUTION_CATALOG if s.resolution]
    assert len(diag_codes) == len(set(diag_codes)), "duplicate diagnostic workflow code"
    assert len(res_codes) == len(set(res_codes)), "duplicate resolution workflow code"
    # The seeder keys three tables by `code`; a collision across the knowledge
    # and workflow namespaces would make seeding non-idempotent.
    assert not set(diag_codes) & set(res_codes)


@pytest.mark.parametrize("spec", RESOLUTION_CATALOG, ids=lambda s: s.code)
def test_every_issue_is_well_formed(spec: KnownIssueSpec):
    assert spec.title and spec.description
    assert spec.category
    assert spec.severity in {s.value for s in IncidentSeverity}
    assert spec.escalation_queue in ESCALATION_QUEUES
    assert spec.symptoms, "an issue with no symptoms cannot be matched by a tech"
    assert spec.probable_causes, "probable_causes drives the recommendation output"
    # Every issue must be actionable — a known issue with no way to diagnose or
    # fix it is knowledge the engine cannot use.
    assert spec.diagnostic is not None
    assert spec.resolution is not None


@pytest.mark.parametrize("spec", RESOLUTION_CATALOG, ids=lambda s: s.code)
def test_every_diagnostic_workflow_is_well_formed(spec: KnownIssueSpec):
    diag = spec.diagnostic
    assert diag.title
    assert diag.escalation_queue in ESCALATION_QUEUES
    assert diag.ordered_steps, "a diagnostic with no steps is not a workflow"
    assert diag.expected_results

    orders = [step["order"] for step in diag.ordered_steps]
    assert orders == list(range(1, len(orders) + 1)), (
        f"{diag.code} steps must be numbered 1..N contiguously, got {orders}"
    )
    for step in diag.ordered_steps:
        assert step["action"].strip()

    for path in diag.failure_paths:
        assert path["when"].strip() and path["do"].strip()
        assert path["escalate_to"] in ESCALATION_QUEUES, (
            f"{diag.code} escalates to unknown queue {path['escalate_to']!r}"
        )


@pytest.mark.parametrize("spec", RESOLUTION_CATALOG, ids=lambda s: s.code)
def test_every_resolution_workflow_is_well_formed(spec: KnownIssueSpec):
    res = spec.resolution
    assert res.title
    assert res.resolution_steps, "a resolution with no steps is not a fix procedure"
    assert res.success_criteria, "without success criteria a tech cannot close the issue"
    assert res.escalation_trigger.strip()
    assert res.estimated_time_minutes > 0

    orders = [step["order"] for step in res.resolution_steps]
    assert orders == list(range(1, len(orders) + 1)), (
        f"{res.code} steps must be numbered 1..N contiguously, got {orders}"
    )
    for step in res.resolution_steps:
        assert step["action"].strip()


def test_catalog_covers_the_four_operational_domains():
    categories = {spec.category for spec in RESOLUTION_CATALOG}
    assert {
        "elevator_phone",
        "fire_alarm_communicator",
        "gate_phone",
        "carrier",
    } <= categories


def test_get_known_issue_by_code():
    spec = get_known_issue("elev_no_dial_tone")
    assert spec is not None
    assert spec.hardware_model == "LM150"
    assert spec.vendor == "FlyingVoice"
    assert get_known_issue("no_such_issue_code") is None


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

def test_outcome_and_queue_value_lists_mirror_the_enums():
    assert OUTCOME_TYPES == [o.value for o in OutcomeType]
    assert ESCALATION_QUEUES == [q.value for q in EscalationQueue]
    assert OutcomeType.RESOLVED.value == "resolved"
    assert EscalationQueue.TIER2_VOICE.value == "Tier2Voice"


def test_severity_is_the_phase_15_enum_not_a_competing_one():
    from app.services.ops_center.intelligence.constants import (
        IncidentSeverity as CanonicalSeverity,
    )

    assert IncidentSeverity is CanonicalSeverity


# ════════════════════════════════════════════════════════════════════
# Deterministic matching
# ════════════════════════════════════════════════════════════════════

def test_matches_on_the_domain_category():
    matches = find_matching_issues(issue_category="elevator_phone")
    assert matches
    assert all("issue_category" in m.reasons for m in matches)
    assert all(m.issue.category == "elevator_phone" for m in matches)


def test_matches_on_an_ops_issue_category_alias():
    """`no_dial_tone` is an Ops Center issue category, not a catalog domain."""
    matches = find_matching_issues(issue_category="no_dial_tone", limit=20)
    codes = {m.issue.code for m in matches}
    assert "elev_no_dial_tone" in codes
    # It reaches across domains — a carrier IMS failure also presents as no dial tone.
    assert "carrier_tmobile_ims_registration_failure" in codes


def test_severity_alone_is_never_a_match():
    """A severity-only coincidence is not a real hit (the strong-dimension rule)."""
    assert find_matching_issues(severity="high") == []
    assert find_matching_issues(severity="critical") == []


def test_severity_refines_but_does_not_create_a_match():
    without = find_matching_issues(issue_category="elevator_phone", limit=20)
    with_sev = find_matching_issues(
        issue_category="elevator_phone", severity="high", limit=20
    )
    assert {m.issue.code for m in without} == {m.issue.code for m in with_sev}


def test_full_match_on_every_provided_dimension_scores_one():
    matches = find_matching_issues(
        issue_category="no_dial_tone",
        vendor="FlyingVoice",
        hardware_model="LM150",
    )
    assert matches[0].issue.code == "elev_no_dial_tone"
    assert matches[0].score == 1.0
    assert set(matches[0].reasons) == {"issue_category", "vendor", "hardware_model"}


def test_partial_match_scores_below_a_full_match():
    matches = find_matching_issues(
        issue_category="no_dial_tone",
        vendor="FlyingVoice",
        hardware_model="LM150",
        limit=20,
    )
    best, rest = matches[0], matches[1:]
    assert best.score == 1.0
    assert rest, "expected weaker partial matches to also be returned"
    assert all(m.score < best.score for m in rest)
    assert matches == sorted(matches, key=lambda m: m.score, reverse=True)


def test_hardware_model_matching_tolerates_a_qualified_name():
    """'NAPCO StarLink' from the field must match the catalog's 'StarLink'."""
    matches = find_matching_issues(vendor="NAPCO", hardware_model="NAPCO StarLink")
    assert matches
    assert matches[0].score == 1.0
    assert {"vendor", "hardware_model"} <= set(matches[0].reasons)


def test_carrier_matching():
    matches = find_matching_issues(carrier="T-Mobile", limit=20)
    assert matches
    assert all("carrier" in m.reasons for m in matches)
    assert all(m.issue.carrier == "T-Mobile" for m in matches)
    assert "carrier_tmobile_activation_failure" in {m.issue.code for m in matches}


def test_unknown_inputs_produce_no_match():
    assert find_matching_issues(
        issue_category="not_a_category",
        carrier="NotACarrier",
        vendor="NotAVendor",
        hardware_model="NotAModel",
    ) == []


def test_no_inputs_produce_no_match():
    assert find_matching_issues() == []


def test_matching_is_deterministic_and_ties_keep_catalog_order():
    first = find_matching_issues(issue_category="fire_alarm_communicator", limit=20)
    second = find_matching_issues(issue_category="fire_alarm_communicator", limit=20)
    assert [m.issue.code for m in first] == [m.issue.code for m in second]
    assert [m.score for m in first] == [m.score for m in second]

    # All ties here — order must follow the catalog's own order.
    assert len({m.score for m in first}) == 1
    catalog_order = [
        s.code for s in RESOLUTION_CATALOG if s.category == "fire_alarm_communicator"
    ]
    assert [m.issue.code for m in first] == catalog_order


def test_limit_is_respected():
    assert len(find_matching_issues(issue_category="elevator_phone", limit=2)) == 2
    assert len(find_matching_issues(issue_category="elevator_phone", limit=1)) == 1


def test_an_injected_catalog_replaces_the_default():
    only = [_spec(code="only_one", category="synthetic_domain")]
    matches = find_matching_issues(issue_category="synthetic_domain", catalog=only)
    assert [m.issue.code for m in matches] == ["only_one"]
    # And the real catalog is not consulted.
    assert find_matching_issues(issue_category="elevator_phone", catalog=only) == []


# ════════════════════════════════════════════════════════════════════
# Recommendation engine
# ════════════════════════════════════════════════════════════════════

def test_recommend_returns_the_full_structured_shape():
    rec = recommend(
        issue_category="no_dial_tone", vendor="FlyingVoice", hardware_model="LM150"
    )
    assert set(rec) == {
        "probable_causes",
        "recommended_diagnostics",
        "recommended_resolutions",
        "recommended_escalation_queue",
        "confidence",
        "matched_issues",
        "note",
    }
    assert rec["probable_causes"]
    assert rec["recommended_diagnostics"]
    assert rec["recommended_resolutions"]
    assert rec["recommended_escalation_queue"] == EscalationQueue.TIER2_VOICE.value
    assert rec["confidence"] == 1.0
    assert rec["matched_issues"][0]["code"] == "elev_no_dial_tone"


def test_recommend_draws_its_content_from_the_best_match():
    best = get_known_issue("elev_no_dial_tone")
    rec = recommend(
        issue_category="no_dial_tone", vendor="FlyingVoice", hardware_model="LM150"
    )
    assert rec["probable_causes"] == list(best.probable_causes)
    assert rec["recommended_diagnostics"] == list(best.diagnostic.ordered_steps)
    assert rec["recommended_resolutions"] == list(best.resolution.resolution_steps)


def test_recommend_confidence_equals_the_best_match_score():
    matches = find_matching_issues(carrier="T-Mobile", limit=5)
    rec = recommend(carrier="T-Mobile", limit=5)
    assert rec["confidence"] == matches[0].score


def test_recommend_with_no_match_is_honest_and_routes_to_a_human():
    rec = recommend(issue_category="not_a_category", vendor="NotAVendor")
    assert rec["confidence"] == 0.0
    assert rec["probable_causes"] == []
    assert rec["recommended_diagnostics"] == []
    assert rec["recommended_resolutions"] == []
    assert rec["recommended_escalation_queue"] is None
    assert rec["matched_issues"] == []
    assert "human queue" in rec["note"]


def test_recommend_is_explainable():
    """Every recommendation must carry the reason codes it was derived from."""
    rec = recommend(
        issue_category="no_dial_tone", vendor="FlyingVoice", hardware_model="LM150"
    )
    top = rec["matched_issues"][0]
    assert set(top["reasons"]) == {"issue_category", "vendor", "hardware_model"}
    assert top["code"] in rec["note"]
    for reason in top["reasons"]:
        assert reason in rec["note"]


def test_recommend_marks_confidence_as_internal_only():
    """§7.1 — confidence is a tech/NOC signal, never a customer-facing status."""
    rec = recommend(issue_category="elevator_phone")
    assert "not a customer-facing status" in rec["note"]


def test_recommend_falls_back_to_the_diagnostic_queue():
    """An issue with no queue of its own inherits the diagnostic's queue."""
    spec = _spec(
        code="queueless",
        escalation_queue=None,
        diagnostic=DiagnosticSpec(
            code="diag_queueless",
            title="Queueless diagnostic",
            ordered_steps=[{"order": 1, "action": "check"}],
            expected_results=["ok"],
            failure_paths=[],
            escalation_queue=EscalationQueue.INSTALLER.value,
        ),
    )
    rec = recommend(issue_category="synthetic_domain", catalog=[spec])
    assert rec["recommended_escalation_queue"] == EscalationQueue.INSTALLER.value


def test_recommend_is_deterministic():
    kwargs = dict(issue_category="device_offline", carrier="Verizon")
    assert recommend(**kwargs) == recommend(**kwargs)


def test_recommend_does_not_mutate_the_catalog():
    best = get_known_issue("elev_no_dial_tone")
    before = list(best.probable_causes)
    rec = recommend(
        issue_category="no_dial_tone", vendor="FlyingVoice", hardware_model="LM150"
    )
    rec["probable_causes"].append("injected")
    rec["recommended_diagnostics"].clear()
    assert best.probable_causes == before
    assert best.diagnostic.ordered_steps


# ════════════════════════════════════════════════════════════════════
# Diagnostic / resolution accessors
# ════════════════════════════════════════════════════════════════════

def test_diagnostic_for_issue():
    diag = diagnostic_for_issue("elev_no_dial_tone")
    assert diag is not None
    assert diag.code == "diag_elev_no_dial_tone"
    assert diagnostic_for_issue("no_such_issue_code") is None


def test_resolution_for_issue():
    res = resolution_for_issue("elev_no_dial_tone")
    assert res is not None
    assert res.estimated_time_minutes > 0
    assert resolution_for_issue("no_such_issue_code") is None


def test_diagnostic_to_dict_shape():
    payload = diagnostic_to_dict(diagnostic_for_issue("elev_no_dial_tone"))
    assert set(payload) == {
        "code",
        "title",
        "ordered_steps",
        "expected_results",
        "failure_paths",
        "escalation_queue",
    }


def test_resolution_to_dict_shape():
    payload = resolution_to_dict(resolution_for_issue("elev_no_dial_tone"))
    assert set(payload) == {
        "code",
        "title",
        "resolution_steps",
        "estimated_time_minutes",
        "escalation_trigger",
        "success_criteria",
    }


# ════════════════════════════════════════════════════════════════════
# Model posture
# ════════════════════════════════════════════════════════════════════

def test_knowledge_tables_carry_no_tenant_id():
    """The library is global operational knowledge, not customer data."""
    for model in (OpsKnownIssue, OpsDiagnosticWorkflow, OpsResolutionWorkflow):
        assert "tenant_id" not in model.__table__.columns, (
            f"{model.__name__} must not be tenant-scoped"
        )


def test_outcome_table_is_tenant_scoped_for_traceability():
    columns = OpsResolutionOutcome.__table__.columns
    assert "tenant_id" in columns
    assert columns["tenant_id"].nullable is True
    assert "session_ref" in columns
    assert columns["tenant_id"].index is True


def test_no_native_pg_enum_columns():
    """Convention: allowed values are enforced in code, not by a DB enum type."""
    for model in (
        OpsKnownIssue,
        OpsDiagnosticWorkflow,
        OpsResolutionWorkflow,
        OpsResolutionOutcome,
    ):
        for column in model.__table__.columns:
            assert column.type.__class__.__name__ != "Enum", (
                f"{model.__name__}.{column.name} uses a native enum"
            )


# ════════════════════════════════════════════════════════════════════
# Idempotent seeder
# ════════════════════════════════════════════════════════════════════

async def test_seed_inserts_the_whole_catalog_into_an_empty_db():
    db = FakeDB(results=[[], [], []])
    inserted = await seed_resolution_intelligence(db)

    expected = len(RESOLUTION_CATALOG)
    assert inserted == {
        "known_issues": expected,
        "diagnostic_workflows": expected,
        "resolution_workflows": expected,
    }
    assert len(db.added_of(OpsKnownIssue)) == expected
    assert len(db.added_of(OpsDiagnosticWorkflow)) == expected
    assert len(db.added_of(OpsResolutionWorkflow)) == expected
    assert db.commits == 1


async def test_seed_is_idempotent_when_everything_is_already_present():
    db = FakeDB(
        results=[
            [s.code for s in RESOLUTION_CATALOG],
            [s.diagnostic.code for s in RESOLUTION_CATALOG],
            [s.resolution.code for s in RESOLUTION_CATALOG],
        ]
    )
    inserted = await seed_resolution_intelligence(db)

    assert inserted == {
        "known_issues": 0,
        "diagnostic_workflows": 0,
        "resolution_workflows": 0,
    }
    assert db.added == []


async def test_seed_inserts_only_what_is_missing():
    present = RESOLUTION_CATALOG[:3]
    db = FakeDB(
        results=[
            [s.code for s in present],
            [s.diagnostic.code for s in present],
            [s.resolution.code for s in present],
        ]
    )
    inserted = await seed_resolution_intelligence(db)

    remaining = len(RESOLUTION_CATALOG) - len(present)
    assert inserted["known_issues"] == remaining
    seeded_codes = {row.code for row in db.added_of(OpsKnownIssue)}
    assert seeded_codes.isdisjoint({s.code for s in present})


async def test_seed_maps_spec_fields_onto_the_row():
    spec = _spec(code="mapped", vendor="Acme", carrier="T-Mobile", hardware_model="X1")
    db = FakeDB(results=[[], [], []])
    await seed_resolution_intelligence(db, catalog=[spec])

    issue = db.added_of(OpsKnownIssue)[0]
    assert issue.code == "mapped"
    assert issue.title == spec.title
    assert issue.category == spec.category
    assert issue.severity == spec.severity
    assert issue.symptoms == list(spec.symptoms)
    assert issue.probable_causes == list(spec.probable_causes)
    assert issue.vendor == "Acme"
    assert issue.carrier == "T-Mobile"
    assert issue.hardware_model == "X1"
    assert issue.active is True

    diag = db.added_of(OpsDiagnosticWorkflow)[0]
    assert diag.code == "diag_mapped"
    assert diag.issue_code == "mapped", "workflows cross-link to the issue by code"
    assert diag.category == spec.category

    res = db.added_of(OpsResolutionWorkflow)[0]
    assert res.code == "res_mapped"
    assert res.issue_code == "mapped"
    assert res.estimated_time_minutes == spec.resolution.estimated_time_minutes


async def test_seed_can_defer_the_commit_to_the_caller():
    db = FakeDB(results=[[], [], []])
    await seed_resolution_intelligence(db, commit=False)
    assert db.added, "rows are still staged"
    assert db.commits == 0


async def test_seed_writes_no_outcome_rows():
    """Seeding loads knowledge only — an outcome is a real engagement result."""
    db = FakeDB(results=[[], [], []])
    await seed_resolution_intelligence(db)
    assert db.added_of(OpsResolutionOutcome) == []
