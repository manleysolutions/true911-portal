"""Migration 055 (D-024): creates exactly the two snapshot tables, fails loudly
on a pre-existing target table, downgrades exactly those two."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

import app.models.source_snapshot  # noqa: F401  (registers the models on Base)
from app.database import Base

_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions",
                     "055_source_snapshots.py")


def _load():
    spec = importlib.util.spec_from_file_location("m055", _PATH)
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
    assert (mod.revision, mod.down_revision) == ("055", "054")
    assert mod.OWNED_TABLES == ("source_snapshots", "source_snapshot_records")


def test_upgrade_matches_the_models():
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        mod = _run(conn, "upgrade")
        insp = sa.inspect(conn)
        for t in mod.OWNED_TABLES:
            table = Base.metadata.tables[t]
            assert {c["name"] for c in insp.get_columns(t)} == set(table.columns.keys()), t
            assert {i.name for i in table.indexes} <= {i["name"] for i in insp.get_indexes(t)}
            uq = {c.name for c in table.constraints if isinstance(c, sa.UniqueConstraint) and c.name}
            assert uq <= {u["name"] for u in insp.get_unique_constraints(t)}


@pytest.mark.parametrize("victim", ["source_snapshots", "source_snapshot_records"])
def test_upgrade_fails_loudly_on_a_preexisting_table(victim):
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE %s (id INTEGER PRIMARY KEY)" % victim))
        with pytest.raises(RuntimeError, match="already exist: %s" % victim):
            _run(conn, "upgrade")
        assert set(sa.inspect(conn).get_table_names()) == {victim}


def test_downgrade_drops_exactly_the_two_tables():
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"))
        _run(conn, "upgrade")
        _run(conn, "downgrade")
        assert sa.inspect(conn).get_table_names() == ["unrelated"]
        _run(conn, "upgrade")
        assert len(sa.inspect(conn).get_table_names()) == 3
