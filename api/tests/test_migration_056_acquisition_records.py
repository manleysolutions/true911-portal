"""Migration 056 (D-031): creates exactly acquisition_records, fails loudly on a
pre-existing table, downgrades exactly that table."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

import app.models.acquisition  # noqa: F401  (registers the model on Base)
from app.database import Base

_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions",
                     "056_acquisition_records.py")


def _load():
    spec = importlib.util.spec_from_file_location("m056", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(conn, fn):
    mod = _load()
    mod.op = Operations(MigrationContext.configure(conn))
    getattr(mod, fn)()
    return mod


def test_revision_chain():
    mod = _load()
    assert (mod.revision, mod.down_revision) == ("056", "055")
    assert mod.OWNED_TABLES == ("acquisition_records",)


def test_upgrade_matches_the_model():
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        _run(conn, "upgrade")
        insp = sa.inspect(conn)
        table = Base.metadata.tables["acquisition_records"]
        assert {c["name"] for c in insp.get_columns("acquisition_records")} == set(table.columns.keys())
        assert {i.name for i in table.indexes} <= {i["name"] for i in insp.get_indexes("acquisition_records")}
        uq = {c.name for c in table.constraints if isinstance(c, sa.UniqueConstraint) and c.name}
        assert uq == {"uq_acquisition_records_record_ref", "uq_acquisition_records_idempotency_key"}
        assert uq <= {u["name"] for u in insp.get_unique_constraints("acquisition_records")}


def test_upgrade_fails_loudly_on_a_preexisting_table():
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE acquisition_records (id INTEGER PRIMARY KEY)"))
        with pytest.raises(RuntimeError, match="already exist: acquisition_records"):
            _run(conn, "upgrade")


def test_downgrade_drops_exactly_the_table():
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"))
        _run(conn, "upgrade")
        _run(conn, "downgrade")
        assert sa.inspect(conn).get_table_names() == ["unrelated"]
