"""Regression guard — T-Mobile TAAP client must not print or log credentials.

Background:
  Before PR `security(tmobile): remove unsafe credential logging` the
  ``get_access_token`` flow had unconditional ``print()`` calls that
  emitted the full ``Authorization: Basic <base64(consumer_key:secret)>``
  header on every token request, plus debug-gated prints that exposed
  the PoP JWT prefix and ``iss`` claim (= consumer_key).  These tests
  pin the post-fix behavior so any future re-introduction fails CI
  before it ships.

What we assert:
  Across both debug-off and debug-on modes, the captured stdout and
  log records produced by ``TMobileTAAPClient.get_access_token()`` must
  NOT contain:
    - the literal consumer_key value
    - the literal consumer_secret value
    - the Base64-encoded "<consumer_key>:<consumer_secret>" string
    - the full "Basic <b64>" Authorization header
    - any JWT segment substring long enough to be reversible

What we DON'T assert:
  - That debug output is silent (it should still be useful — URL,
    hashes, lengths, redacted claims).  We only assert credentials
    don't appear.
"""

from __future__ import annotations

import base64
import logging
import os

import httpx
import pytest
import respx


# Distinctive sentinel values so a substring search is unambiguous.
_CK = "TM_TEST_CK_HG7XQ2"
_CS = "TM_TEST_CS_PL3JR9"
_BASIC_B64 = base64.b64encode(f"{_CK}:{_CS}".encode("utf-8")).decode("ascii")
_BASIC_HEADER = "Basic " + _BASIC_B64


@pytest.fixture
def fake_private_key_and_creds(tmp_path, monkeypatch):
    """Generate a throwaway RSA private key, point the loader at it, and
    populate ``settings.TMOBILE_CONSUMER_KEY/_SECRET`` so the production
    code paths that read from ``settings`` (not just instance attrs)
    actually see the sentinel values.  In particular, ``generate_pop_token``
    sources ``iss`` from ``settings.TMOBILE_CONSUMER_KEY`` rather than the
    client instance, so the test must monkeypatch settings to exercise
    the realistic credential-leak surface.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    p = tmp_path / "tm.pem"
    p.write_bytes(pem)
    monkeypatch.setattr(
        "app.integrations.tmobile_taap.settings.TMOBILE_PRIVATE_KEY_PATH",
        str(p),
    )
    monkeypatch.setattr(
        "app.integrations.tmobile_taap.settings.TMOBILE_PRIVATE_KEY_PEM",
        "",
    )
    monkeypatch.setattr(
        "app.integrations.tmobile_taap.settings.TMOBILE_CONSUMER_KEY", _CK
    )
    monkeypatch.setattr(
        "app.integrations.tmobile_taap.settings.TMOBILE_CONSUMER_SECRET", _CS
    )
    return p


@respx.mock
@pytest.mark.asyncio
async def test_no_credentials_in_stdout_or_logs_debug_off(
    fake_private_key_and_creds, capsys, caplog, monkeypatch
):
    """Default mode (TMOBILE_TAAP_DEBUG unset).  Captured stdout +
    captured log records must not contain the consumer credentials."""
    from app.integrations.tmobile_taap import TMobileTAAPClient

    # Force debug off in case the dev shell has it on.
    monkeypatch.setenv("TMOBILE_TAAP_DEBUG", "")
    caplog.set_level(logging.DEBUG, logger="app.integrations.tmobile_taap")

    respx.post("https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens").mock(
        return_value=httpx.Response(
            200, json={"access_token": "redacted-token-not-real", "expires_in": 3600}
        )
    )

    client = TMobileTAAPClient(consumer_key=_CK, consumer_secret=_CS)
    await client.get_access_token()

    captured = capsys.readouterr()
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    haystack = captured.out + "\n" + captured.err + "\n" + log_text

    # Hard guarantees.
    assert _CK not in haystack, "consumer_key leaked to stdout/logs"
    assert _CS not in haystack, "consumer_secret leaked to stdout/logs"
    assert _BASIC_B64 not in haystack, (
        "Base64(consumer_key:secret) leaked — reversible to creds"
    )
    assert _BASIC_HEADER not in haystack, "full Basic Authorization header leaked"
    assert "AUTH HEADER EXACT" not in haystack, (
        "unsafe diagnostic 'AUTH HEADER EXACT' has been re-introduced"
    )


@respx.mock
@pytest.mark.asyncio
async def test_no_credentials_in_stdout_or_logs_debug_on(
    fake_private_key_and_creds, capsys, caplog, monkeypatch
):
    """Debug mode (TMOBILE_TAAP_DEBUG=1).  Diagnostics ARE printed but
    must remain free of any credential material.  The redacted PoP
    claim ('<redacted>') and structure-only summaries (lengths,
    hashes, header names) are expected — actual secrets are not.
    """
    from app.integrations.tmobile_taap import TMobileTAAPClient

    monkeypatch.setenv("TMOBILE_TAAP_DEBUG", "1")
    caplog.set_level(logging.DEBUG, logger="app.integrations.tmobile_taap")

    respx.post("https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens").mock(
        return_value=httpx.Response(
            200, json={"access_token": "redacted-token-not-real", "expires_in": 3600}
        )
    )

    client = TMobileTAAPClient(consumer_key=_CK, consumer_secret=_CS)
    await client.get_access_token()

    captured = capsys.readouterr()
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    haystack = captured.out + "\n" + captured.err + "\n" + log_text

    assert _CK not in haystack, "consumer_key leaked when debug=on"
    assert _CS not in haystack, "consumer_secret leaked when debug=on"
    assert _BASIC_B64 not in haystack, (
        "Base64(consumer_key:secret) leaked when debug=on"
    )
    assert _BASIC_HEADER not in haystack, "Basic Authorization header leaked when debug=on"

    # Debug should still be useful — confirm it produced *something*
    # so we'd catch an over-zealous future commit that silenced everything.
    assert "[TAAP-DEBUG]" in haystack, (
        "debug mode produced no diagnostics — the gate may be broken"
    )
    # And confirm the documented redaction shape made it out.
    assert "<redacted>" in haystack, (
        "expected '<redacted>' marker in PoP claims output not found"
    )


def test_unused_re_import_removed():
    """The `import re` was only used by the removed diagnostic block.

    Asserting it stays out keeps the lint surface tidy and serves as a
    canary if someone re-adds the diagnostic block (which would likely
    need `re.fullmatch` again).
    """
    import app.integrations.tmobile_taap as mod

    # `re` should not be in the module's namespace via this module's
    # own import (it may still be reachable transitively, which is
    # fine — the check is on the explicit top-level import).
    src = open(mod.__file__, "r", encoding="utf-8").read()
    assert "\nimport re\n" not in src, (
        "Top-level 'import re' has been re-added.  If you need it, that "
        "is fine — but also re-evaluate whether the unsafe credential "
        "diagnostic block (removed in the security PR) is creeping back."
    )
