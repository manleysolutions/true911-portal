"""Operator tool: reissue an invite for an inactive customer user.

Covers eligibility (inactive + CUSTOMER_* only) and the reissue itself
(dry-run writes nothing; --apply mints a NEW token + expiry and changes nothing
else — role/tenant/identity/activation untouched).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from scripts import reissue_customer_invite as ri


# ── Pure eligibility ─────────────────────────────────────────────────
def test_eligibility_ok_for_inactive_customer():
    u = SimpleNamespace(is_active=False, role="CUSTOMER_ADMIN")
    assert ri.eligibility(u) is None


def test_eligibility_refuses_missing_user():
    assert "no invite-pending customer user" in ri.eligibility(None)


def test_eligibility_refuses_active_user():
    u = SimpleNamespace(is_active=True, role="CUSTOMER_ADMIN")
    assert "active" in ri.eligibility(u)


def test_eligibility_refuses_non_customer_role():
    for role in ("Admin", "User", "Manager", "DataSteward"):
        u = SimpleNamespace(is_active=False, role=role)
        assert "not a customer-plane role" in ri.eligibility(u)


# ── reissue() with a fake DB ─────────────────────────────────────────
class _Res:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDB:
    def __init__(self, row):
        self._row = row
        self.committed = 0

    async def execute(self, stmt):
        return _Res(self._row)

    async def commit(self):
        self.committed += 1


def _user(**kw):
    base = dict(email="judy@rh.example", role="CUSTOMER_ADMIN", tenant_id="restoration-hardware",
                is_active=False, invite_token="OLD-TOKEN", invite_expires_at=None,
                name="Judy", password_hash="HASH")
    base.update(kw)
    return SimpleNamespace(**base)


def test_dry_run_writes_nothing():
    u = _user()
    db = _FakeDB(u)
    out = asyncio.run(ri.reissue(db, email="judy@rh.example", tenant="restoration-hardware", apply=False))
    assert out["status"] == "dry_run"
    assert db.committed == 0
    assert u.invite_token == "OLD-TOKEN"           # untouched in dry-run


def test_apply_mints_new_token_only():
    u = _user()
    db = _FakeDB(u)
    out = asyncio.run(ri.reissue(db, email="JUDY@rh.example", tenant="restoration-hardware", apply=True))
    assert out["status"] == "reissued" and db.committed == 1
    # a NEW token was minted + expiry set
    assert u.invite_token != "OLD-TOKEN" and u.invite_token == out["invite_token"]
    assert u.invite_expires_at is not None
    # identity / role / tenant / activation are UNCHANGED
    assert u.role == "CUSTOMER_ADMIN" and u.tenant_id == "restoration-hardware"
    assert u.email == "judy@rh.example" and u.name == "Judy"
    assert u.is_active is False and u.password_hash == "HASH"


def test_apply_refused_for_active_user_no_write():
    u = _user(is_active=True)
    db = _FakeDB(u)
    out = asyncio.run(ri.reissue(db, email="judy@rh.example", tenant="restoration-hardware", apply=True))
    assert out["status"] == "refused" and db.committed == 0
    assert u.invite_token == "OLD-TOKEN"


def test_apply_refused_for_non_customer_role_no_write():
    u = _user(role="Admin")
    db = _FakeDB(u)
    out = asyncio.run(ri.reissue(db, email="judy@rh.example", tenant="restoration-hardware", apply=True))
    assert out["status"] == "refused" and db.committed == 0


def test_refused_when_user_not_in_tenant():
    # tenant-scoped query -> no row -> refused (never reveals another tenant's user)
    db = _FakeDB(None)
    out = asyncio.run(ri.reissue(db, email="judy@rh.example", tenant="acme", apply=True))
    assert out["status"] == "refused" and db.committed == 0
