"""Zoho CRM fetch_records pagination — page numbers + page_token cursor (read-only).

Regression cover for DISCRETE_PAGINATION_LIMIT_EXCEEDED: past the first 2000
records Zoho requires cursor pagination via ``page_token``.  ``fetch_records`` must
start on page numbers (cheap for small sets) and switch to ``page_token`` as soon
as Zoho returns ``info.next_page_token`` — always preserving ``fields`` and never
writing.
"""

from __future__ import annotations

import asyncio

from app.services import zoho_crm


def _mock_get(monkeypatch, responses):
    """Patch the authenticated GET layer; record every params dict it was called
    with.  ``responses`` is a list of Zoho ``data``/``info`` payloads, one per call."""
    calls = []
    seq = list(responses)

    async def _fake_get(path, params=None):
        calls.append(dict(params or {}))
        return seq.pop(0)

    monkeypatch.setattr(zoho_crm, "is_configured", lambda: True)
    monkeypatch.setattr(zoho_crm, "_zoho_get", _fake_get)
    return calls


def test_single_page_no_more_records(monkeypatch):
    calls = _mock_get(monkeypatch, [
        {"data": [{"id": "1"}, {"id": "2"}], "info": {"more_records": False}},
    ])
    out = asyncio.run(zoho_crm.fetch_records("Accounts", fields="Account_Name"))
    assert [r["id"] for r in out] == ["1", "2"]
    assert len(calls) == 1
    assert calls[0]["page"] == 1 and "page_token" not in calls[0]
    assert calls[0]["fields"] == "Account_Name"       # fields preserved


def test_multi_page_via_next_page_token(monkeypatch):
    calls = _mock_get(monkeypatch, [
        {"data": [{"id": "1"}], "info": {"more_records": True, "next_page_token": "TOK1"}},
        {"data": [{"id": "2"}], "info": {"more_records": True, "next_page_token": "TOK2"}},
        {"data": [{"id": "3"}], "info": {"more_records": False}},
    ])
    out = asyncio.run(zoho_crm.fetch_records("Accounts", fields="Account_Name"))
    assert [r["id"] for r in out] == ["1", "2", "3"]
    # first call uses page number; subsequent calls use the cursor token (no page)
    assert calls[0].get("page") == 1 and "page_token" not in calls[0]
    assert calls[1].get("page_token") == "TOK1" and "page" not in calls[1]
    assert calls[2].get("page_token") == "TOK2" and "page" not in calls[2]


def test_transition_page_then_token(monkeypatch):
    """A first page that uses legacy more_records, then Zoho hands back a token —
    the helper must switch cleanly to cursor mode."""
    calls = _mock_get(monkeypatch, [
        {"data": [{"id": "1"}], "info": {"more_records": True}},                      # page mode
        {"data": [{"id": "2"}], "info": {"more_records": True, "next_page_token": "TOK"}},  # token appears
        {"data": [{"id": "3"}], "info": {"more_records": False}},                     # cursor continues
    ])
    out = asyncio.run(zoho_crm.fetch_records("Contacts"))
    assert [r["id"] for r in out] == ["1", "2", "3"]
    assert calls[0].get("page") == 1                  # legacy page pagination
    assert calls[1].get("page") == 2 and "page_token" not in calls[1]
    assert calls[2].get("page_token") == "TOK" and "page" not in calls[2]


def test_fields_preserved_with_page_token(monkeypatch):
    calls = _mock_get(monkeypatch, [
        {"data": [{"id": "1"}], "info": {"more_records": True, "next_page_token": "TOK1"}},
        {"data": [{"id": "2"}], "info": {"more_records": False}},
    ])
    asyncio.run(zoho_crm.fetch_records("Accounts", fields="Account_Name,Phone"))
    assert calls[0]["fields"] == "Account_Name,Phone"
    assert calls[1]["fields"] == "Account_Name,Phone"     # fields still sent in cursor mode
    assert calls[1]["page_token"] == "TOK1"


def test_max_pages_guard(monkeypatch):
    # never-ending token stream is bounded by max_pages (runaway guard)
    async def _fake_get(path, params=None):
        return {"data": [{"id": "x"}], "info": {"more_records": True, "next_page_token": "T"}}
    monkeypatch.setattr(zoho_crm, "is_configured", lambda: True)
    monkeypatch.setattr(zoho_crm, "_zoho_get", _fake_get)
    out = asyncio.run(zoho_crm.fetch_records("Accounts", max_pages=5))
    assert len(out) == 5                              # stopped at max_pages


def test_page_mode_stops_at_discrete_limit(monkeypatch):
    """Legacy page pagination (no token) must not cross the 2000-record limit."""
    async def _fake_get(path, params=None):
        # 200 records per page, always claims more but never returns a token
        return {"data": [{"id": i} for i in range(200)], "info": {"more_records": True}}
    monkeypatch.setattr(zoho_crm, "is_configured", lambda: True)
    monkeypatch.setattr(zoho_crm, "_zoho_get", _fake_get)
    out = asyncio.run(zoho_crm.fetch_records("Accounts", per_page=200))
    assert len(out) == 2000                           # capped at the discrete limit, no error


def test_not_configured_raises(monkeypatch):
    monkeypatch.setattr(zoho_crm, "is_configured", lambda: False)
    try:
        asyncio.run(zoho_crm.fetch_records("Accounts"))
        assert False, "expected ZohoCRMError"
    except zoho_crm.ZohoCRMError:
        pass
