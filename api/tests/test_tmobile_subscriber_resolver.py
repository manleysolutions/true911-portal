"""Tests for app.services.tmobile_subscriber — per-ICCID account-ID resolution
for QuerySubscriber (Gap #1).

Proves:
  * A SubscriberInquiry by ICCID uses the account ID STORED on sims.meta
    (per-ICCID), not the global env account ID.
  * Account ID resolves from the flat meta key, falling back to the
    tmobile_activation lifecycle record.
  * MSISDN resolves from meta, falling back to the Sim's own column.
  * The live call is gated behind TMOBILE_PIT_LIVE_CALLS_ENABLED.
  * Missing account ID / Sim / MSISDN fail with clear errors and no call.
  * The low-level subscriber_inquiry() neither requires nor transmits an
    account id — it identifies the line by msisdn / iccid / imsi.

No real T-Mobile credentials and no network: the DB is mocked and the TAAP
client is a stub.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import tmobile_activation as activation
from app.services import tmobile_subscriber as subscriber


# ─── builders ───────────────────────────────────────────────────────


def _sim(*, iccid="8901260963132697538", msisdn=None, meta=None,
         tenant_id="tenant-x", device_id="dev-a"):
    return SimpleNamespace(
        iccid=iccid, msisdn=msisdn, meta=meta,
        tenant_id=tenant_id, device_id=device_id,
    )


def _db_returning(sim):
    res = MagicMock()
    res.scalar_one_or_none.return_value = sim
    db = MagicMock()
    db.execute = AsyncMock(return_value=res)
    return db


class _FakeClient:
    """Stub TAAP client — records the SubscriberInquiry args."""

    def __init__(self, result=None):
        self.subscriber_inquiry = AsyncMock(return_value=result or {"status": "active"})
        self.close = AsyncMock()


@pytest.fixture
def live_on(monkeypatch):
    monkeypatch.setattr("app.config.settings.TMOBILE_PIT_LIVE_CALLS_ENABLED", "true")


@pytest.fixture
def live_off(monkeypatch):
    monkeypatch.setattr("app.config.settings.TMOBILE_PIT_LIVE_CALLS_ENABLED", "false")


# ─── pure resolution helpers ────────────────────────────────────────


class TestPureResolution:
    def test_account_id_from_flat_meta(self):
        sim = _sim(meta={"tmobile_account_id": "ACC-789"})
        assert subscriber.account_id_from_sim(sim) == "ACC-789"

    def test_account_id_falls_back_to_activation_record(self):
        sim = _sim(meta={"tmobile_activation": {"account_id": "ACC-REC"}})
        assert subscriber.account_id_from_sim(sim) == "ACC-REC"

    def test_account_id_absent_returns_none(self):
        assert subscriber.account_id_from_sim(_sim(meta=None)) is None
        assert subscriber.account_id_from_sim(_sim(meta={})) is None

    def test_msisdn_prefers_meta_then_column(self):
        assert subscriber.msisdn_from_sim(
            _sim(meta={"tmobile_msisdn": "7542697860"}, msisdn="0000000000")
        ) == "7542697860"
        assert subscriber.msisdn_from_sim(
            _sim(meta={}, msisdn="1112223333")
        ) == "1112223333"
        assert subscriber.msisdn_from_sim(_sim(meta=None, msisdn=None)) is None


# ─── query_subscriber_by_iccid ──────────────────────────────────────


class TestQueryByIccid:
    @pytest.mark.asyncio
    async def test_uses_stored_account_id_for_iccid(self, live_on):
        sim = _sim(meta={"tmobile_account_id": "ACC-789",
                         "tmobile_msisdn": "7542697860"})
        db = _db_returning(sim)
        client = _FakeClient(result={"status": "active", "iccid": sim.iccid})

        result = await subscriber.query_subscriber_by_iccid(
            db, sim.iccid, client=client)

        assert result["status"] == "active"
        # The headline assertion: the STORED per-ICCID account ID was used.
        client.subscriber_inquiry.assert_awaited_once_with(
            "7542697860", account_id="ACC-789")
        # Caller-provided client must NOT be closed by the resolver.
        client.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_account_id_from_activation_record_is_used(self, live_on):
        sim = _sim(
            msisdn="5551230000",
            meta={"tmobile_activation": {"account_id": "ACC-REC", "msisdn": None}},
        )
        db = _db_returning(sim)
        client = _FakeClient()

        await subscriber.query_subscriber_by_iccid(db, sim.iccid, client=client)

        # account_id from the record; msisdn falls back to the Sim column.
        client.subscriber_inquiry.assert_awaited_once_with(
            "5551230000", account_id="ACC-REC")

    @pytest.mark.asyncio
    async def test_gated_by_live_flag(self, live_off):
        sim = _sim(meta={"tmobile_account_id": "ACC-789", "tmobile_msisdn": "7"})
        db = _db_returning(sim)
        client = _FakeClient()

        with pytest.raises(RuntimeError, match="TMOBILE_PIT_LIVE_CALLS_ENABLED"):
            await subscriber.query_subscriber_by_iccid(db, sim.iccid, client=client)
        client.subscriber_inquiry.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_when_no_account_id_yet(self, live_on):
        sim = _sim(meta={"tmobile_msisdn": "7542697860"})  # no account id
        db = _db_returning(sim)
        client = _FakeClient()

        with pytest.raises(RuntimeError, match="No T-Mobile account ID stored"):
            await subscriber.query_subscriber_by_iccid(db, sim.iccid, client=client)
        client.subscriber_inquiry.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_when_no_sim(self, live_on):
        db = _db_returning(None)
        client = _FakeClient()

        with pytest.raises(ValueError, match="No Sim found"):
            await subscriber.query_subscriber_by_iccid(db, "8901999", client=client)
        client.subscriber_inquiry.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_when_no_msisdn(self, live_on):
        sim = _sim(msisdn=None, meta={"tmobile_account_id": "ACC-789"})
        db = _db_returning(sim)
        client = _FakeClient()

        with pytest.raises(ValueError, match="No MSISDN"):
            await subscriber.query_subscriber_by_iccid(db, sim.iccid, client=client)
        client.subscriber_inquiry.assert_not_called()


# ─── low-level subscriber_inquiry: account id is neither required nor sent ───


class TestSubscriberInquiryTakesNoAccountId:
    """SubscriberInquiry identifies the line, not the account.

    These tests previously asserted that an account ID was merged into the
    request body — from the per-call argument, else from the env — and that the
    call was "disabled until an account ID exists". None of that was ever in the
    vendor contract: the operation takes one of msisdn / iccid / imsi and has no
    account-id field. The ``account_id`` keyword survives only so existing
    callers (the per-ICCID resolver above) keep working; it is accepted and
    discarded.
    """

    @pytest.mark.asyncio
    async def test_passed_account_id_is_accepted_but_never_transmitted(self):
        """Changed: the body carries only the identifier — no accountId key.

        The old assertion pinned an accountId into the payload, which the
        vendor contract does not define for this operation.
        """
        from app.integrations.tmobile_taap import TMobileTAAPClient
        client = TMobileTAAPClient(
            consumer_key="ck", consumer_secret="cs", account_id="ENV-ACC")
        client._request = AsyncMock(return_value={"ok": True})

        await client.subscriber_inquiry("5550001234", account_id="PER-ICCID")

        body = client._request.call_args.kwargs["json_body"]
        assert body == {"msisdn": "5550001234"}
        assert "accountId" not in body
        assert "PER-ICCID" not in str(body)

    @pytest.mark.asyncio
    async def test_env_account_id_is_not_merged_into_the_body(self):
        """Changed: there is no env fallback because there is no field to fill."""
        from app.integrations.tmobile_taap import TMobileTAAPClient
        client = TMobileTAAPClient(
            consumer_key="ck", consumer_secret="cs", account_id="ENV-ACC")
        client._request = AsyncMock(return_value={"ok": True})

        await client.subscriber_inquiry(iccid="8901260963132600001")

        body = client._request.call_args.kwargs["json_body"]
        assert body == {"iccid": "8901260963132600001"}
        assert "ENV-ACC" not in str(body)

    @pytest.mark.asyncio
    async def test_an_identifier_is_required_not_an_account_id(self):
        """Changed: the mandatory input is an identifier, not an account ID.

        With no account ID at all the call is well-formed; what is refused is a
        call that names no subscriber.
        """
        from app.integrations.tmobile_taap import TMobileTAAPClient
        client = TMobileTAAPClient(
            consumer_key="ck", consumer_secret="cs", account_id="")
        client._request = AsyncMock(return_value={"ok": True})

        # No account ID, but an identifier — accepted.
        await client.subscriber_inquiry(imsi="310260000000001")
        assert client._request.call_args.kwargs["json_body"] == {
            "imsi": "310260000000001"}

        # No identifier at all — refused before anything is built or sent.
        client._request.reset_mock()
        with pytest.raises(ValueError, match="msisdn, iccid, or imsi"):
            await client.subscriber_inquiry()
        client._request.assert_not_called()
