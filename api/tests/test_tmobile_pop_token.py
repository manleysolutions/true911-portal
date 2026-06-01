"""Known-answer tests for the T-Mobile TAAP PoP token algorithm.

Pins the canonicalization required by T-Mobile's pop-token-builder so the
"Security-1017 Invalid PoP Token" class of failure cannot regress:

  * ehts  = the signed keys joined by a SEMICOLON  (";")
  * edts  = base64url( SHA-256( value1 + value2 + ... ) )  with NO separator
            between the concatenated values
  * uri          is one of the signed ehts keys (its value participates in edts)
  * http-method  is one of the signed ehts keys (its value participates in edts)
  * JWT header   uses alg=RS256 and the signature verifies with the matching
                 public key (RS256 round-trip)

Reference vector (T-Mobile PoP docs):
  ehts        = "Content-Type;uri;http-method"
  edtsString  = "application/json" + "/oauth2/v2/tokens" + "POST"
              = "application/json/oauth2/v2/tokensPOST"
  edts        = "tpAdmPMl2Q_2fRUR4OEflknZQtyTYh_rKqV3yqbDZA0"

Scope note: this test deliberately does NOT assert the JWT `typ` value or the
`v` (version) claim — those remediation steps are intentionally deferred. The
test pins only the four changes under implementation: ";"-delimited ehts,
no-separator edts, uri signing, and http-method signing.
"""

from __future__ import annotations

import base64
import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt

import app.integrations.tmobile_taap as taap

# T-Mobile published reference inputs (token POST).
REFERENCE_EHTS = [
    ("Content-Type", "application/json"),
    ("uri", "/oauth2/v2/tokens"),
    ("http-method", "POST"),
]
EXPECTED_EHTS = "Content-Type;uri;http-method"
EXPECTED_EDTS = "tpAdmPMl2Q_2fRUR4OEflknZQtyTYh_rKqV3yqbDZA0"


@pytest.fixture
def signing_key(monkeypatch):
    """Throwaway RSA key wired into the PoP signer (no env / no secrets touched)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    monkeypatch.setattr(taap, "_load_private_key", lambda: pem)
    return pem


def _claims(pop):
    return jose_jwt.get_unverified_claims(pop)


def _header(pop):
    return jose_jwt.get_unverified_header(pop)


class TestPopKnownAnswer:
    def test_ehts_is_semicolon_delimited(self, signing_key):
        pop = taap.generate_pop_token(ehts_headers=REFERENCE_EHTS)
        assert _claims(pop)["ehts"] == EXPECTED_EHTS

    def test_edts_matches_published_known_answer(self, signing_key):
        pop = taap.generate_pop_token(ehts_headers=REFERENCE_EHTS)
        assert _claims(pop)["edts"] == EXPECTED_EDTS

    def test_edts_is_no_separator_sha256_base64url(self, signing_key):
        # Independent oracle — concatenate values with NO separator.
        concat = "".join(v for _, v in REFERENCE_EHTS)
        oracle = (
            base64.urlsafe_b64encode(hashlib.sha256(concat.encode()).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        assert oracle == EXPECTED_EDTS  # sanity-check the constant itself
        pop = taap.generate_pop_token(ehts_headers=REFERENCE_EHTS)
        assert _claims(pop)["edts"] == oracle

    def test_uri_value_is_signed(self, signing_key):
        ehts = _claims(taap.generate_pop_token(ehts_headers=REFERENCE_EHTS))["ehts"]
        assert "uri" in ehts.split(";")
        # Changing only the uri value must change edts -> it participates in the hash.
        base_edts = _claims(taap.generate_pop_token(ehts_headers=REFERENCE_EHTS))["edts"]
        alt = [("Content-Type", "application/json"), ("uri", "/oauth2/v1/tokens"), ("http-method", "POST")]
        alt_edts = _claims(taap.generate_pop_token(ehts_headers=alt))["edts"]
        assert base_edts != alt_edts

    def test_http_method_value_is_signed(self, signing_key):
        ehts = _claims(taap.generate_pop_token(ehts_headers=REFERENCE_EHTS))["ehts"]
        assert "http-method" in ehts.split(";")
        base_edts = _claims(taap.generate_pop_token(ehts_headers=REFERENCE_EHTS))["edts"]
        alt = [("Content-Type", "application/json"), ("uri", "/oauth2/v2/tokens"), ("http-method", "GET")]
        alt_edts = _claims(taap.generate_pop_token(ehts_headers=alt))["edts"]
        assert base_edts != alt_edts

    def test_jwt_header_alg_rs256_and_signature_verifies(self, signing_key):
        pop = taap.generate_pop_token(ehts_headers=REFERENCE_EHTS)
        assert _header(pop)["alg"] == "RS256"
        assert pop.count(".") == 2  # header.payload.signature
        # RS256 round-trip: verifies with the public key derived from the signer.
        pub_pem = (
            serialization.load_pem_private_key(signing_key.encode(), password=None)
            .public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
        decoded = jose_jwt.decode(
            pop, pub_pem, algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": False},
        )
        assert decoded["ehts"] == EXPECTED_EHTS
        assert decoded["edts"] == EXPECTED_EDTS
