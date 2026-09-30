"""A real (in-memory SQLite) database harness for customer-plane tests.

Most suites here mock the query seams; the self-service work needs genuine
reads-after-writes, unique constraints and tenant filters to be exercised, so
this builds ONLY the tables the customer plane touches on an aiosqlite engine
and serves the real routers through an in-process ASGI client — everything on
one event loop per test (``asyncio.run``).

Postgres-only column types (JSONB on ServiceUnit) compile to SQLite ``JSON``
via a test-only ``@compiles`` shim; nothing here changes production DDL.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_current_user, get_db
from app.models.action_audit import ActionAudit
from app.models.customer import Customer
from app.models.customer_self_service import (
    CustomerActivityEvent,
    CustomerManagedField,
    CustomerServiceRequest,
)
from app.models.device import Device
from app.models.e911_change_log import E911ChangeLog
from app.models.line import Line
from app.models.portfolio_registry import (
    PortfolioAlias,
    PortfolioBuilding,
    PortfolioDeviceMapping,
    PortfolioReviewItem,
)
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.models.tenant import Tenant


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(_type, _compiler, **_kw):   # test-only shim
    return "JSON"


TABLES = [m.__table__ for m in (
    Tenant, Customer, Site, Device, Line, ServiceUnit, ActionAudit, E911ChangeLog,
    PortfolioBuilding, PortfolioAlias, PortfolioDeviceMapping, PortfolioReviewItem,
    CustomerServiceRequest, CustomerManagedField, CustomerActivityEvent,
)]


async def make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))
    return engine, async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def user(role="CUSTOMER_ADMIN", tenant="restoration-hardware", email="judy@rh.example",
         name="Judy"):
    return SimpleNamespace(role=role, tenant_id=tenant, email=email, name=name, id=1,
                           is_active=True)


def client_for(routers, sessionmaker, state) -> httpx.AsyncClient:
    """An ASGI client over the real routers; ``state['user']`` is the caller."""
    app = FastAPI()
    for router, prefix in routers:
        app.include_router(router, prefix=prefix)

    async def _db():
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
