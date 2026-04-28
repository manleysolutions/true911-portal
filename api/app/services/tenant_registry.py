"""Tenant-bearing model registry.

Single source of truth for migration scripts that need to operate on
every model carrying a ``tenant_id`` column.  Replaces the hand-typed
table lists that bit us in the past (e.g. importing
``Integration`` instead of ``IntegrationAccount`` because both classes
live in the same module file).

Usage from a script under ``scripts/`` that sets up sys.path to
include ``api/``::

    from app.services.tenant_registry import tenant_models

    for table_name, model in tenant_models():
        await db.execute(
            update(model)
            .where(model.tenant_id == FROM_TENANT)
            .values(tenant_id=TO_TENANT)
        )
"""

from __future__ import annotations

import importlib
import pkgutil

import app.models  # package handle — used below to walk submodules
from app.database import Base
from app.models.tenant import Tenant


def _ensure_all_models_imported() -> None:
    """Walk every submodule under ``app.models`` and import it.

    SQLAlchemy mapper registration happens as a side effect of importing
    a model module.  Relying on ``app.models.__init__`` to import every
    submodule has bitten us before (e.g. ``command_activity.py`` was
    silently missing from ``__init__.py``, so its mapper never
    registered for callers who only imported the package).  Walking the
    directory removes that risk and keeps the registry honest.
    """
    for _finder, name, _ispkg in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module(f"app.models.{name}")


_ensure_all_models_imported()


def tenant_models() -> list[tuple[str, type]]:
    """Return ``[(table_name, mapped_class)]`` for every mapped model
    whose table has a ``tenant_id`` column, **excluding the ``Tenant``
    model itself**.

    Output is sorted by table name so iteration order is stable across
    runs and easy to diff in dry-run logs.

    The Tenant exclusion is intentional: ``Tenant.tenant_id`` is the
    tenant *slug* (the join key), not a foreign reference to another
    tenant.  Including it in a tenant-move script would silently
    rewrite the slug and corrupt every relationship.
    """
    out: list[tuple[str, type]] = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if cls is Tenant:
            continue
        table = mapper.local_table
        if table is None:
            continue
        if "tenant_id" in table.columns:
            out.append((table.name, cls))
    return sorted(out, key=lambda kv: kv[0])
