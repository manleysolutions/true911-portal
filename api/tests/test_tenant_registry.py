"""Lock the contract of ``app.services.tenant_registry.tenant_models()``.

The migration scripts (``scripts/dedupe_tenant_rh.py`` and
``scripts/consolidate_rh_to_default.py``) consume this helper to decide
which tables to update during a tenant move.  These tests pin the
helper's behavior so a future model-package refactor can't silently
hide a model from the move list.
"""

from __future__ import annotations

import pytest

from app.database import Base
from app.models.tenant import Tenant
from app.services.tenant_registry import tenant_models


# Models that have ``tenant_id`` and have historically been in scope for
# tenant-move scripts.  If any of these stops being discovered, a real
# data table will be silently skipped during the next migration.
_MUST_BE_PRESENT = {
    "users",
    "customers",
    "sites",
    "devices",
    "sims",
    "lines",
    "service_units",
    "incidents",
    "events",
    "command_notifications",
    "command_activities",     # the one that bit us — was missing from app/models/__init__.py
    "command_telemetry",
    "integration_accounts",   # tenant-bearing child of integrations
    "audit_log_entries",
    "action_audits",
}

# Models that should NEVER appear in the registry's output.
_MUST_NOT_BE_PRESENT = {
    "tenants",       # the Tenant table — its tenant_id is the slug, not an FK reference
    "integrations",  # parent class without a tenant_id column
}


def _names() -> list[str]:
    return [name for name, _cls in tenant_models()]


def test_helper_returns_nonempty_sorted_list():
    out = tenant_models()
    assert out, "tenant_models() must not be empty"
    names = [name for name, _cls in out]
    assert names == sorted(names), "tenant_models() must be sorted by table name"


def test_every_returned_model_has_tenant_id_column():
    """The whole point of the helper — never include a model whose
    table lacks a ``tenant_id`` column."""
    for name, cls in tenant_models():
        table = cls.__table__
        assert "tenant_id" in table.columns, (
            f"{cls.__name__} ({name}) returned by tenant_models() but its "
            "table has no tenant_id column"
        )


def test_returned_classes_are_unique():
    """No duplicate class entries — guards against a future refactor
    that double-registers a mapper."""
    classes = [cls for _name, cls in tenant_models()]
    assert len(classes) == len(set(classes)), "duplicate model classes returned"


def test_table_names_are_unique():
    names = _names()
    assert len(names) == len(set(names)), "duplicate table names returned"


@pytest.mark.parametrize("table_name", sorted(_MUST_BE_PRESENT))
def test_known_tenant_tables_are_present(table_name: str):
    assert table_name in _names(), (
        f"{table_name!r} must be discovered by tenant_models() — it has a "
        "tenant_id column and tenant-move scripts depend on it"
    )


@pytest.mark.parametrize("table_name", sorted(_MUST_NOT_BE_PRESENT))
def test_known_excluded_tables_are_absent(table_name: str):
    assert table_name not in _names(), (
        f"{table_name!r} must NOT be discovered by tenant_models() — it has "
        "no tenant_id column or is the Tenant table itself"
    )


def test_tenant_table_excluded_by_class_identity():
    """The Tenant model is excluded explicitly even though
    ``tenants.tenant_id`` exists as a column.  Pin the contract."""
    classes = [cls for _name, cls in tenant_models()]
    assert Tenant not in classes


def test_directory_walk_picks_up_models_outside_init():
    """Regression test for the ``command_activity.py`` omission from
    ``app/models/__init__.py``.  The helper must walk the package
    directory directly so a model module that nobody remembered to
    add to ``__init__`` still gets registered."""
    assert "command_activities" in _names(), (
        "command_activities must be discovered even when "
        "app/models/__init__.py doesn't import command_activity. "
        "If this fails, _ensure_all_models_imported() likely got "
        "removed or broken."
    )


def test_returned_count_matches_metadata_truth():
    """Cross-check: the count from the helper must match an
    independent count of mapped tables that have a tenant_id column,
    minus the Tenant exclusion."""
    expected_count = sum(
        1
        for mapper in Base.registry.mappers
        if mapper.class_ is not Tenant
        and mapper.local_table is not None
        and "tenant_id" in mapper.local_table.columns
    )
    assert len(tenant_models()) == expected_count
