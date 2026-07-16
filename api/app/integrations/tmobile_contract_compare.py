"""Compare a local sanitized evidence exchange against a known-good reference.

Answers one question: **where does our request differ from T-Mobile's?**

Both inputs are sanitized evidence documents (the shape produced by
``tmobile_evidence.capture_request``). No secrets or tokens are read or printed —
the comparison works on header NAMES, allowlisted header VALUES, ehts order, PoP
structure, and body digests.

Difference severities:
  - ``mismatch``  — both sides have the field, values differ
  - ``missing``   — the reference has it, we do not
  - ``extra``     — we have it, the reference does not
  - ``ordering``  — same members, different order (ehts order is contractual)
  - ``assumption``— we cannot verify this from the evidence; flagged, never guessed
"""

from __future__ import annotations

from typing import Any

# Header values worth comparing directly. Anything credential-bearing is compared
# on PRESENCE only, never value.
_COMPARE_HEADER_VALUES = (
    "Content-Type", "Accept", "grant-type", "sender-id", "partner-id",
    "call-back-location", "X-Account-Id",
)
# Per-request-unique values: comparing them across two different requests is
# meaningless (they SHOULD differ), so compare presence only.
_PRESENCE_ONLY_VALUES = ("partner-transaction-id", "X-Correlation-Id")


def _diff(kind: str, field: str, ours: Any, theirs: Any, note: str = "") -> dict[str, Any]:
    return {
        "severity": kind, "field": field,
        "ours": ours, "reference": theirs, "note": note,
    }


def _get(doc: dict[str, Any], *path: str, default: Any = None) -> Any:
    node: Any = doc
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _lower_map(values: dict[str, str] | None) -> dict[str, tuple[str, str]]:
    """name.lower() -> (original_name, value)."""
    return {k.lower(): (k, v) for k, v in (values or {}).items()}


def compare_requests(
    ours: dict[str, Any], reference: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compare two sanitized request captures. Returns the differences."""
    out: list[dict[str, Any]] = []

    # ── URL / path / method ──────────────────────────────────────────────
    for field in ("method", "path"):
        a, b = ours.get(field), reference.get(field)
        if a != b:
            out.append(_diff("mismatch", field, a, b))
    if ours.get("url") != reference.get("url"):
        out.append(_diff(
            "mismatch", "url", ours.get("url"), reference.get("url"),
            "Query values are redacted in both; a difference here is host/path.",
        ))

    # ── Header names ─────────────────────────────────────────────────────
    our_names = {n.lower() for n in _get(ours, "headers", "names", default=[]) or []}
    ref_names = {n.lower() for n in _get(reference, "headers", "names", default=[]) or []}
    for name in sorted(ref_names - our_names):
        out.append(_diff("missing", f"header:{name}", None, "<present>",
                         "The reference sends this header and we do not."))
    for name in sorted(our_names - ref_names):
        out.append(_diff("extra", f"header:{name}", "<present>", None,
                         "We send this header and the reference does not."))

    # Exact spelling matters (T-Mobile requires lowercase `sender-id`).
    our_spelling = {n.lower(): n for n in _get(ours, "headers", "names", default=[]) or []}
    ref_spelling = {n.lower(): n for n in _get(reference, "headers", "names", default=[]) or []}
    for lowered in sorted(set(our_spelling) & set(ref_spelling)):
        if our_spelling[lowered] != ref_spelling[lowered]:
            out.append(_diff(
                "mismatch", f"header-name-case:{lowered}",
                our_spelling[lowered], ref_spelling[lowered],
                "Header NAME spelling differs; T-Mobile requires exact case.",
            ))

    # ── Safe header values ───────────────────────────────────────────────
    ours_v = _lower_map(_get(ours, "headers", "safe_values", default={}))
    ref_v = _lower_map(_get(reference, "headers", "safe_values", default={}))
    for name in _COMPARE_HEADER_VALUES:
        key = name.lower()
        a = ours_v.get(key, (None, None))[1]
        b = ref_v.get(key, (None, None))[1]
        if a is None and b is None:
            continue
        if a != b:
            out.append(_diff("mismatch", f"header-value:{name}", a, b))
    for name in _PRESENCE_ONLY_VALUES:
        key = name.lower()
        a, b = key in ours_v, key in ref_v
        if a != b:
            out.append(_diff(
                "mismatch", f"header-presence:{name}", a, b,
                "Per-request unique value — presence compared, not the value.",
            ))

    # ── Credential-bearing headers: presence only ────────────────────────
    our_p = _get(ours, "headers", "presence", default={}) or {}
    ref_p = _get(reference, "headers", "presence", default={}) or {}
    for name in sorted(set(our_p) | set(ref_p)):
        a, b = our_p.get(name, False), ref_p.get(name, False)
        if a != b:
            out.append(_diff("mismatch", f"header-presence:{name}", a, b,
                             "Value never compared — presence only."))

    # ── PoP: JWT header, claims, ehts order, edts ────────────────────────
    out.extend(_compare_pop(_get(ours, "pop", default={}) or {},
                            _get(reference, "pop", default={}) or {}))

    # ── Body digest ──────────────────────────────────────────────────────
    a_len = _get(ours, "body", "byte_length")
    b_len = _get(reference, "body", "byte_length")
    if a_len != b_len:
        out.append(_diff("mismatch", "body.byte_length", a_len, b_len))
    a_sha = _get(ours, "body", "sha256")
    b_sha = _get(reference, "body", "sha256")
    if a_sha != b_sha:
        out.append(_diff(
            "mismatch", "body.sha256", a_sha, b_sha,
            "Bodies differ. If byte_length matches, suspect whitespace or key "
            "order — the PoP signs the exact bytes.",
        ))
    elif a_sha is None and b_sha is None:
        out.append(_diff(
            "assumption", "body.sha256", None, None,
            "Neither side recorded a body digest — body equality NOT verified.",
        ))

    return out


def _compare_pop(ours: dict[str, Any], ref: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not ref:
        return out
    if not ours.get("present") and ref.get("present"):
        out.append(_diff("missing", "pop", None, "<present>",
                         "The reference carries a PoP and we do not."))
        return out

    a_hdr, b_hdr = ours.get("jwt_header"), ref.get("jwt_header")
    if a_hdr != b_hdr:
        out.append(_diff("mismatch", "pop.jwt_header", a_hdr, b_hdr))

    a_names = ours.get("ehts_names") or []
    b_names = ref.get("ehts_names") or []
    if a_names != b_names:
        if sorted(a_names) == sorted(b_names):
            out.append(_diff(
                "ordering", "pop.ehts", ";".join(a_names), ";".join(b_names),
                "Same keys, different ORDER. edts concatenates values in ehts "
                "order, so the order is contractual.",
            ))
        else:
            for name in sorted(set(b_names) - set(a_names)):
                out.append(_diff("missing", f"pop.ehts:{name}", None, name))
            for name in sorted(set(a_names) - set(b_names)):
                note = ""
                if name.lower() == "sender-id":
                    note = ("sender-id must be UNSIGNED — T-Mobile confirmed it "
                            "must not appear in the PoP ehts.")
                out.append(_diff("extra", f"pop.ehts:{name}", name, None, note))

    a_claims = set(ours.get("claims") or {})
    b_claims = set(ref.get("claims") or {})
    for name in sorted(b_claims - a_claims):
        out.append(_diff("missing", f"pop.claim:{name}", None, "<present>"))
    for name in sorted(a_claims - b_claims):
        out.append(_diff("extra", f"pop.claim:{name}", "<present>", None))

    a_life, b_life = ours.get("lifetime_seconds"), ref.get("lifetime_seconds")
    if a_life != b_life and b_life is not None:
        out.append(_diff("mismatch", "pop.lifetime_seconds", a_life, b_life))

    if ours.get("edts") and ref.get("edts") and ours["edts"] != ref["edts"]:
        out.append(_diff(
            "mismatch", "pop.edts", ours["edts"], ref["edts"],
            "Digests differ — expected whenever any signed value differs "
            "(tokens/bodies differ between two real requests, so this alone is "
            "not necessarily a defect).",
        ))
    return out


def render_report(diffs: list[dict[str, Any]]) -> str:
    """Human-readable comparison report. Prints no secrets."""
    if not diffs:
        return "MATCH — no differences found in the compared fields."

    order = {"mismatch": 0, "missing": 1, "extra": 2, "ordering": 3, "assumption": 4}
    lines = ["REQUEST CONTRACT COMPARISON", "=" * 60]
    for sev in sorted({d["severity"] for d in diffs}, key=lambda s: order.get(s, 9)):
        group = [d for d in diffs if d["severity"] == sev]
        lines.append("")
        lines.append(f"{sev.upper()} ({len(group)})")
        lines.append("-" * 60)
        for d in group:
            lines.append(f"  {d['field']}")
            lines.append(f"    ours:      {d['ours']!r}")
            lines.append(f"    reference: {d['reference']!r}")
            if d["note"]:
                lines.append(f"    note: {d['note']}")
    lines.append("")
    lines.append(f"{len(diffs)} difference(s). No secrets or tokens were compared.")
    return "\n".join(lines)
