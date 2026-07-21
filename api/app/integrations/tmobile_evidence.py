"""Sanitized outbound-request capture for T-Mobile PIT diagnostics.

Produces evidence bundles that are safe to paste into an email to T-Mobile while
containing everything needed to diagnose a wire-contract mismatch.

Design rule — **allowlist, never denylist**. Header values are captured only if
the name appears in ``SAFE_HEADER_VALUES``; everything else is reduced to a
presence flag. A future header carrying a secret is therefore redacted by
DEFAULT rather than leaking until someone remembers to add it to a blocklist.

Never captured, by construction:
  - the Basic Authorization value (base64-reversible to key:secret)
  - the Bearer access token, the id_token, the X-Authorization PoP JWT
  - the consumer secret, the private key, the raw cnf public key
  - request/response body CONTENT (length + SHA-256 only)

The one exception is operator-supplied test identifiers (e.g. the ICCID passed
explicitly to a PIT activation), which are recorded because T-Mobile needs them
to find the call in their logs. They are passed in deliberately — never scraped
out of a body.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from jose import jwt as jose_jwt

# ── Header classification ───────────────────────────────────────────────────

# Non-secret routing/diagnostic headers whose VALUES are safe to record.
SAFE_HEADER_VALUES: tuple[str, ...] = (
    "Content-Type",
    "Accept",
    "grant-type",
    "sender-id",
    "partner-id",
    "partner-transaction-id",
    "X-Correlation-Id",
    "call-back-location",
    "X-Account-Id",
)

# Credential-bearing headers — presence only, value NEVER recorded.
PRESENCE_ONLY_HEADERS: tuple[str, ...] = (
    "Authorization",
    "X-Authorization",
    "X-Auth-Originator",
)

# PoP claims safe to record. edts is a SHA-256 digest (not reversible); ehts is
# a list of header NAMES. Anything outside this set is dropped rather than
# guessed at — e.g. a resurrected `iss` would carry the consumer key.
SAFE_POP_CLAIMS: tuple[str, ...] = ("iat", "exp", "ehts", "edts", "jti", "v")

# Response body keys that must be masked if a body ever echoes them back.
_SENSITIVE_BODY_KEYS = frozenset({
    "access_token", "id_token", "refresh_token", "cnf",
    "client_secret", "consumer_secret", "authorization",
})

_RESPONSE_BODY_LIMIT = 2000

_WORKFLOW_ID_HEADERS = (
    "work-flow-id", "x-work-flow-id", "workflow-id", "x-workflow-id",
)
_SERVICE_TXN_HEADERS = ("service-transaction-id", "x-service-transaction-id")
_PARTNER_TXN_HEADERS = (
    "partner-transaction-id", "x-partner-transaction-id",
    "transaction-id", "x-transaction-id",
)


def utc_now_iso() -> str:
    """UTC timestamp, e.g. 2026-07-16T20:39:07.197374Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def utc_stamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _redact_url(url: str) -> str:
    """Return the URL with every query VALUE masked (names kept).

    A query value can carry a token; the names alone are enough to diagnose a
    routing problem.
    """
    parts = urlsplit(url)
    if not parts.query:
        return url
    redacted = "&".join(f"{k}=<redacted>" for k, _ in parse_qsl(parts.query))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, redacted, ""))


def sanitize_headers(headers: Any) -> dict[str, Any]:
    """Split headers into safe values, presence flags, and names.

    Matching is case-insensitive; the ORIGINAL spelling is reported, because the
    lowercase-vs-capitalized distinction is itself contractual here (T-Mobile
    requires lowercase `sender-id`).

    Reads ``headers.raw`` when available: httpx's ``.items()`` lowercases names,
    which would silently destroy the very casing this capture exists to prove.
    """
    raw = getattr(headers, "raw", None)
    if raw:
        items = [
            (n.decode("latin-1") if isinstance(n, bytes) else str(n),
             v.decode("latin-1") if isinstance(v, bytes) else str(v))
            for n, v in raw
        ]
    else:
        try:
            items = list(headers.items())
        except AttributeError:
            items = list(dict(headers or {}).items())

    safe_lookup = {n.lower(): n for n in SAFE_HEADER_VALUES}
    presence_lookup = {n.lower(): n for n in PRESENCE_ONLY_HEADERS}

    values: dict[str, str] = {}
    presence: dict[str, bool] = {n: False for n in PRESENCE_ONLY_HEADERS}
    names: list[str] = []

    for raw_name, raw_value in items:
        name = str(raw_name)
        names.append(name)
        lowered = name.lower()
        if lowered in safe_lookup:
            values[name] = str(raw_value)
        elif lowered in presence_lookup:
            presence[presence_lookup[lowered]] = True

    return {
        "names": names,
        "safe_values": values,
        "presence": presence,
    }


def describe_pop(pop_jwt: str | None) -> dict[str, Any]:
    """Decode a PoP JWT into its safe structural facts.

    Records the JWT header, the safe claims, and the ehts/edts. The JWT itself is
    never recorded.
    """
    if not pop_jwt:
        return {"present": False}
    try:
        header = jose_jwt.get_unverified_header(pop_jwt)
        claims = jose_jwt.get_unverified_claims(pop_jwt)
    except Exception as exc:  # malformed PoP is itself the finding
        return {"present": True, "decode_error": type(exc).__name__}

    safe_claims = {k: v for k, v in claims.items() if k in SAFE_POP_CLAIMS}
    dropped = sorted(set(claims) - set(SAFE_POP_CLAIMS))
    ehts = str(safe_claims.get("ehts", ""))
    out: dict[str, Any] = {
        "present": True,
        "jwt_header": dict(header),
        "claims": safe_claims,
        "ehts": ehts,
        "ehts_names": [n for n in ehts.split(";") if n],
        "edts": safe_claims.get("edts"),
        "lifetime_seconds": (
            safe_claims["exp"] - safe_claims["iat"]
            if "exp" in safe_claims and "iat" in safe_claims else None
        ),
    }
    if dropped:
        # Surfaced (names only) so an unexpected claim is visible, not silent.
        out["unexpected_claims_dropped"] = dropped
    return out


def _digest(body: bytes | None) -> dict[str, Any]:
    data = body or b""
    return {
        "byte_length": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def capture_request(request: Any, *, env: str) -> dict[str, Any]:
    """Capture one outbound httpx request, sanitized.

    Body CONTENT is never recorded — only its exact byte length and SHA-256,
    which is what proves the signed bytes equal the sent bytes.
    """
    headers = sanitize_headers(request.headers)
    body = request.content or b""
    return {
        "captured_at_utc": utc_now_iso(),
        "environment": env,
        "method": request.method.upper(),
        "url": _redact_url(str(request.url)),
        "path": request.url.path,
        "headers": headers,
        "body": _digest(body),
        "pop": describe_pop(request.headers.get("X-Authorization")),
    }


def _redact_body_text(text: str) -> str:
    """Truncate a response body and mask any credential-bearing JSON values."""
    try:
        parsed = json.loads(text)
    except ValueError:
        return text[:_RESPONSE_BODY_LIMIT]

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                k: ("<redacted>" if k.lower() in _SENSITIVE_BODY_KEYS else _walk(v))
                for k, v in node.items()
            }
        if isinstance(node, list):
            return [_walk(v) for v in node]
        return node

    return json.dumps(_walk(parsed))[:_RESPONSE_BODY_LIMIT]


def _first_header(headers: Any, candidates: tuple[str, ...]) -> str | None:
    getter = getattr(headers, "get", None) or dict(headers or {}).get
    for name in candidates:
        val = getter(name)
        if val:
            return str(val)
    return None


def capture_response(response: Any) -> dict[str, Any]:
    """Capture one response, sanitized — status + the ids T-Mobile correlates on."""
    return {
        "status_code": response.status_code,
        "work_flow_id": _first_header(response.headers, _WORKFLOW_ID_HEADERS),
        "service_transaction_id": _first_header(response.headers, _SERVICE_TXN_HEADERS),
        "partner_transaction_id": _first_header(response.headers, _PARTNER_TXN_HEADERS),
        "body": _redact_body_text(response.text or ""),
    }


class EvidenceRecorder:
    """Attaches to a TMobileTAAPClient and records every outbound exchange.

    Observes what was ACTUALLY sent (via httpx event hooks) rather than
    re-deriving it, so the evidence cannot silently agree with a broken client —
    the failure mode that let six PoP defects survive three review rounds.
    """

    def __init__(self, env: str):
        self.env = env
        self.exchanges: list[dict[str, Any]] = []
        self._pending: dict[int, dict[str, Any]] = {}

    def attach(self, client: Any) -> None:
        """Pre-seed the client's HTTP client with capture hooks.

        TMobileTAAPClient._client() reuses an already-open instance, so seeding
        it here is the supported injection point.
        """
        import httpx

        async def _on_request(request: httpx.Request) -> None:
            self._pending[id(request)] = capture_request(request, env=self.env)

        async def _on_response(response: httpx.Response) -> None:
            await response.aread()  # body needed for the sanitized excerpt
            entry = self._pending.pop(id(response.request), None) or {}
            self.exchanges.append({
                "request": entry,
                "response": capture_response(response),
            })

        client._http = httpx.AsyncClient(
            timeout=30.0,
            event_hooks={"request": [_on_request], "response": [_on_response]},
        )

    def finalize(self) -> list[dict[str, Any]]:
        # A request that never got a response (connect error/timeout) still
        # belongs in the bundle — its absence would be the finding.
        for entry in self._pending.values():
            self.exchanges.append({"request": entry, "response": None})
        self._pending.clear()
        return self.exchanges


def _bundle_skeleton(client: Any, mode: str) -> dict[str, Any]:
    return {
        "schema": "true911.tmobile.pit-evidence/1",
        "mode": mode,
        "generated_at_utc": utc_now_iso(),
        "environment": getattr(client, "base_url", ""),
        "token_url": getattr(client, "token_url", ""),
        "partner_id": getattr(client, "partner_id", "") or None,
        "sender_id": getattr(client, "sender_id", "") or None,
        "partner_foundation": partner_foundation_status(client),
        "live_calls_enabled": type(client).live_calls_enabled(),
        "exchanges": [],
        "notes": [],
    }


async def run_token_only(client: Any) -> dict[str, Any]:
    """One OAuth token request. Sends NO activation and no resource call."""
    bundle = _bundle_skeleton(client, "token-only")
    recorder = EvidenceRecorder(env=client.base_url)
    recorder.attach(client)
    try:
        await client.get_access_token()
        bundle["ok"] = True
        bundle["id_token_returned"] = bool(getattr(client, "_id_token", None))
    except Exception as exc:
        bundle["ok"] = False
        # The message may embed the response body; it is sanitized on the way in.
        bundle["error"] = _redact_body_text(str(exc))
    finally:
        bundle["exchanges"] = recorder.finalize()
        await client.close()
    bundle["notes"].append("Token-only: no activation and no resource call was sent.")
    return bundle


async def run_activation_preview(
    client: Any, *, iccid: str, market_zip: str | None = None
) -> dict[str, Any]:
    """Build the exact activation request WITHOUT any network call.

    No OAuth, no signing against a live token, nothing transmitted.
    """
    bundle = _bundle_skeleton(client, "activation-preview")
    preview = client.build_activation_preview(iccid, market_zip=market_zip)

    # Reproduce the exact bytes _request() would serialize and sign.
    body_str = json.dumps(preview["payload"], separators=(",", ":"))
    body_bytes = body_str.encode("utf-8")

    bundle["iccid"] = iccid  # operator-supplied test identifier
    bundle["request_preview"] = {
        "method": preview["method"],
        "url": _redact_url(preview["url"]),
        "path": preview["path"],
        "header_names": sorted(preview["headers"]),
        "safe_header_values": {
            k: v for k, v in preview["headers"].items()
            if k.lower() in {n.lower() for n in SAFE_HEADER_VALUES}
        },
        "body": _digest(body_bytes),
        "expected_pop_ehts_names": preview["pop_signed_ehts"],
        "expected_pop_ehts": ";".join(preview["pop_signed_ehts"]),
        "callback_location_configured": preview["callback_location_configured"],
    }
    bundle["ok"] = True
    bundle["notes"].extend(preview["notes"])
    bundle["notes"].append(
        "Activation-preview: NOTHING was sent — no OAuth, no activation."
    )
    return bundle


async def run_activation(
    client: Any, *, iccid: str, market_zip: str | None, confirm_live: bool
) -> dict[str, Any]:
    """Send EXACTLY ONE activation. Never retries.

    Two independent gates, both required:
      1. ``confirm_live`` — the operator's explicit --confirm-live at the CLI
      2. ``TMOBILE_PIT_LIVE_CALLS_ENABLED=true`` — enforced inside the client
    """
    if not confirm_live:
        raise RuntimeError(
            "Refusing to send: --confirm-live was not passed. No request was made."
        )
    if not type(client).live_calls_enabled():
        raise RuntimeError(
            "Refusing to send: TMOBILE_PIT_LIVE_CALLS_ENABLED is not true. "
            "No request was made."
        )

    bundle = _bundle_skeleton(client, "activate")
    bundle["iccid"] = iccid  # operator-supplied test identifier
    recorder = EvidenceRecorder(env=client.base_url)
    recorder.attach(client)
    try:
        result = await client.activate_subscriber(iccid, market_zip=market_zip)
        bundle["ok"] = True
        bundle["result"] = _redact_body_text(json.dumps(result))
    except Exception as exc:
        # A 400 is the expected outcome right now — the bundle IS the deliverable,
        # so preserve every correlation id rather than letting the raise discard it.
        bundle["ok"] = False
        bundle["error"] = _redact_body_text(str(exc))
    finally:
        bundle["exchanges"] = recorder.finalize()
        await client.close()
    bundle["notes"].append(
        "Exactly one activation was attempted. No automatic retry — investigate "
        "before sending another."
    )
    return bundle


def render_text_report(bundle: dict[str, Any]) -> str:
    """Render a paste-into-email report. Contains no secrets."""
    L: list[str] = []
    L.append("T-MOBILE PIT EVIDENCE")
    L.append("=" * 60)
    L.append(f"Mode:            {bundle['mode']}")
    L.append(f"Generated (UTC): {bundle['generated_at_utc']}")
    L.append(f"Base URL:        {bundle['environment']}")
    L.append(f"Token URL:       {bundle['token_url']}")
    L.append(f"partner-id:      {bundle.get('partner_id')}")
    L.append(f"sender-id:       {bundle.get('sender_id')}")
    if bundle.get("iccid"):
        L.append(f"ICCID:           {bundle['iccid']}")
    L.append(f"Live calls:      {bundle['live_calls_enabled']}")
    L.append(f"Outcome:         {'OK' if bundle.get('ok') else 'FAILED'}")

    pf = bundle["partner_foundation"]
    L.append("")
    L.append("PARTNER FOUNDATION ID")
    L.append("-" * 60)
    L.append(f"  configured value:  {pf['configured_value']}")
    L.append(f"  configured header: {pf['configured_header_name']}")
    L.append(f"  sent on requests:  {pf['sent_on_requests']}")
    L.append(f"  {pf['note']}")

    if bundle.get("request_preview"):
        p = bundle["request_preview"]
        L.append("")
        L.append("ACTIVATION REQUEST (PREVIEW — NOT SENT)")
        L.append("-" * 60)
        L.append(f"  {p['method']} {p['url']}")
        L.append(f"  body bytes:  {p['body']['byte_length']}")
        L.append(f"  body SHA-256: {p['body']['sha256']}")
        L.append(f"  expected PoP ehts: {p['expected_pop_ehts']}")
        for k, v in sorted(p["safe_header_values"].items()):
            L.append(f"  {k}: {v}")

    for i, ex in enumerate(bundle.get("exchanges", []), 1):
        req, resp = ex.get("request") or {}, ex.get("response")
        L.append("")
        L.append(f"EXCHANGE {i}")
        L.append("-" * 60)
        L.append(f"  {req.get('method')} {req.get('url')}")
        L.append(f"  sent at (UTC): {req.get('captured_at_utc')}")
        for k, v in sorted((req.get("headers") or {}).get("safe_values", {}).items()):
            L.append(f"  {k}: {v}")
        for k, v in sorted((req.get("headers") or {}).get("presence", {}).items()):
            L.append(f"  {k}: {'<present, redacted>' if v else '<absent>'}")
        body = req.get("body") or {}
        L.append(f"  body bytes: {body.get('byte_length')}")
        L.append(f"  body SHA-256: {body.get('sha256')}")
        pop = req.get("pop") or {}
        if pop.get("present"):
            L.append(f"  PoP jwt header: {pop.get('jwt_header')}")
            L.append(f"  PoP ehts: {pop.get('ehts')}")
            L.append(f"  PoP edts: {pop.get('edts')}")
            L.append(f"  PoP lifetime (s): {pop.get('lifetime_seconds')}")
            L.append(f"  PoP claims: {pop.get('claims')}")
        if resp is None:
            L.append("  response: <none — no response received>")
        else:
            L.append(f"  RESPONSE status: {resp['status_code']}")
            L.append(f"  work-flow-id: {resp['work_flow_id']}")
            L.append(f"  service-transaction-id: {resp['service_transaction_id']}")
            L.append(f"  partner-transaction-id: {resp['partner_transaction_id']}")
            L.append(f"  body: {resp['body']}")

    if bundle.get("error"):
        L.append("")
        L.append(f"ERROR: {bundle['error']}")

    if bundle.get("notes"):
        L.append("")
        L.append("NOTES")
        L.append("-" * 60)
        for n in bundle["notes"]:
            L.append(f"  - {n}")

    L.append("")
    L.append("No tokens, keys, or Basic credentials appear in this report.")
    return "\n".join(L)


def write_evidence(bundle: dict[str, Any], out_dir: str) -> tuple[str, str]:
    """Write the JSON + text bundle. Returns (json_path, txt_path)."""
    import os

    os.makedirs(out_dir, exist_ok=True)
    stamp = utc_stamp_for_filename()
    base = os.path.join(out_dir, f"tmobile-pit-evidence-{stamp}")
    json_path, txt_path = f"{base}.json", f"{base}.txt"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, sort_keys=True)
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(render_text_report(bundle))
    return json_path, txt_path


def mask_tail(value: str | None, *, keep: int = 4) -> str | None:
    """Mask an identifier down to its last ``keep`` characters.

    Used for MSISDN / ICCID / account IDs in BROADLY VISIBLE artifacts (committed
    fixtures, PR bodies, the audit doc). The last four digits are enough for an
    operator to confirm they are looking at the right line; the full value lives
    only in the restricted operator record.

    Distinct from ``tmobile_callback_processor._redact_identifier``, which keeps
    the leading six characters because a log reader needs the carrier prefix.
    Here the prefix is exactly what we do not want to publish.
    """
    if not value:
        return None
    text = str(value)
    if len(text) <= keep:
        return "*" * len(text)
    return "*" * (len(text) - keep) + text[-keep:]


def build_success_record(
    *,
    activated_at_utc: str,
    endpoint: str,
    http_status: int,
    response_body: dict[str, Any] | str,
    iccid: str,
    partner_transaction_id: str,
    correlation_id: str,
    work_flow_id: str | None,
    service_transaction_id: str | None,
    oauth_service_transaction_id: str | None = None,
    deployment_commit: str,
    request_headers: Any,
    partner_foundation_header_sent: bool = False,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Build the committed, sanitized record of a SUCCESSFUL PIT activation.

    Every identifier that could be considered subscriber-identifying is reduced
    to its last four characters by :func:`mask_tail` before it enters the record,
    and the response body passes through :func:`_redact_body_text` so a body that
    ever echoes a credential key is masked by the same rules as a live capture.
    Headers are classified by the same allowlist as a live capture
    (:func:`sanitize_headers`), so an unrecognised header's value is dropped by
    DEFAULT rather than published.

    This is a reconstruction from the operator's runner output, not a second
    capture — ``source`` records that explicitly so the artifact never reads as
    more authoritative than it is.
    """
    body_text = (
        response_body if isinstance(response_body, str)
        else json.dumps(response_body, separators=(",", ":"))
    )
    sanitized_body = json.loads(_redact_body_text(body_text))

    results = sanitized_body.get("result") or []
    result_codes = [str(r.get("result")) for r in results if isinstance(r, dict)]

    return {
        "schema": "true911.tmobile.pit-success/1",
        "source": (
            "Reconstructed from the operator's tmobile_pit_evidence.py --activate "
            "bundle. The raw bundle was written to the operator's temp directory "
            "and is not committed; this record is the sanitized, masked subset."
        ),
        "outcome": "SUCCESS",
        "activated_at_utc": activated_at_utc,
        "deployment_commit": deployment_commit,
        "endpoint": endpoint,
        "http_status": http_status,
        "response": {
            "status": sanitized_body.get("status"),
            "result_codes": result_codes,
            "msisdn_masked": mask_tail(sanitized_body.get("msisdn")),
            "iccid_masked": mask_tail(sanitized_body.get("iccid")),
            "account_id_masked": mask_tail(sanitized_body.get("accountId")),
        },
        "request": {
            "iccid_masked": mask_tail(iccid),
            "headers": sanitize_headers(request_headers),
        },
        "trace": {
            "partner_transaction_id": partner_transaction_id,
            "correlation_id": correlation_id,
            "work_flow_id": work_flow_id,
            "service_transaction_id": service_transaction_id,
            "oauth_service_transaction_id": oauth_service_transaction_id,
        },
        "partner_foundation": {
            "configured_value": None,
            "configured_header_name": None,
            "sent_on_requests": partner_foundation_header_sent,
            "note": (
                "No Partner Foundation header was configured or transmitted on "
                "the successful request. The activation succeeded without it."
            ),
        },
        "notes": notes or [],
    }


def partner_foundation_status(client: Any) -> dict[str, Any]:
    """Report Partner Foundation config state WITHOUT sending anything.

    The value is an opaque partner identifier (like partner-id 128), not a
    credential, so it is safe to echo back to T-Mobile in an evidence bundle —
    that is the point: Aman can confirm whether the value we hold is right.
    """
    value = getattr(client, "partner_foundation_id", "") or ""
    header = getattr(client, "partner_foundation_header", "") or ""
    return {
        "configured_value": value or None,
        "configured_header_name": header or None,
        "sent_on_requests": False,
        "note": (
            "CONFIGURATION ONLY — never transmitted. The header name, whether it "
            "replaces or supplements partner-id, its scope (OAuth/resource/both), "
            "and whether it is signed all require T-Mobile confirmation. Nothing "
            "is guessed."
        ),
    }
