"""Migration 054 (D-023): creates exactly the eight canonical tables, fails
loudly on any pre-existing target table, downgrades exactly those eight."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

import app.models.canonical  # noqa: F401  (registers the models on Base)
from app.database import Base

_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions",
                     "054_canonical_service_model.py")


def _load():
    spec = importlib.util.spec_from_file_location("m054", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(conn, fn_name):
    mod = _load()
    mod.op = Operations(MigrationContext.configure(conn))
    getattr(mod, fn_name)()
    return mod


def test_revision_chain():
    mod = _load()
    assert (mod.revision, mod.down_revision) == ("054", "053")
    assert len(mod.OWNED_TABLES) == 8


def test_upgrade_creates_all_eight_matching_the_models():
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"))
        mod = _run(conn, "upgrade")
        insp = sa.inspect(conn)
        assert set(mod.OWNED_TABLES) <= set(insp.get_table_names())
        for t in mod.OWNED_TABLES:
            table = Base.metadata.tables[t]
            assert {c["name"] for c in insp.get_columns(t)} == set(table.columns.keys()), t
            model_ix = {i.name for i in table.indexes}
            mig_ix = {i["name"] for i in insp.get_indexes(t)}
            assert model_ix <= mig_ix, (t, model_ix - mig_ix)
            model_uq = {c.name for c in table.constraints
                        if isinstance(c, sa.UniqueConstraint) and c.name}
            mig_uq = {u["name"] for u in insp.get_unique_constraints(t)}
            assert model_uq <= mig_uq, (t, model_uq - mig_uq)


@pytest.mark.parametrize("victim", ["projection_runs", "life_safety_connections",
                                    "operator_decisions"])
def test_upgrade_fails_loudly_on_a_preexisting_canonical_table(victim):
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE %s (id INTEGER PRIMARY KEY)" % victim))
        with pytest.raises(RuntimeError, match="already exist: %s" % victim):
            _run(conn, "upgrade")
        # nothing else was created - the unknown table was not adopted
        assert set(sa.inspect(conn).get_table_names()) == {victim}


def test_downgrade_drops_exactly_the_eight_tables():
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"))
        _run(conn, "upgrade")
        _run(conn, "downgrade")
        assert sa.inspect(conn).get_table_names() == ["unrelated"]
        _run(conn, "upgrade")                       # clean re-upgrade after downgrade
        assert len(sa.inspect(conn).get_table_names()) == 9
