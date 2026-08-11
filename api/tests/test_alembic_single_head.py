"""Structural guard on the Alembic revision graph.

A branched migration chain (two revisions sharing one ``down_revision``) is not
a syntax error and no existing test caught it — it surfaced only as an
``alembic upgrade head`` failure at deploy time, and it blocked unrelated work
for weeks because migration ownership became ambiguous.  These tests read the
version files directly (no DB, no Alembic import) and fail fast on a fork.
"""

from __future__ import annotations

import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"

# Both declaration styles appear in the history: bare (`revision = "052"`) and
# annotated (`revision: str = "001"` / `down_revision: Union[str, None] = None`).
_REVISION_RE = re.compile(
    r"^revision(?:\s*:[^=]+)?\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE
)
_DOWN_REVISION_RE = re.compile(
    r"^down_revision(?:\s*:[^=]+)?\s*=\s*(?:[\"']([^\"']+)[\"']|None)", re.MULTILINE
)


def _load_revisions() -> dict[str, str | None]:
    """Map every revision id → its down_revision (``None`` for the base)."""
    revisions: dict[str, str | None] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        text = path.read_text(encoding="utf-8")
        rev_match = _REVISION_RE.search(text)
        assert rev_match, f"{path.name} defines no `revision`"
        down_match = _DOWN_REVISION_RE.search(text)
        assert down_match, f"{path.name} defines no `down_revision`"
        rev = rev_match.group(1)
        assert rev not in revisions, f"duplicate revision id {rev!r} in {path.name}"
        revisions[rev] = down_match.group(1)  # None when the literal was `None`
    return revisions


def test_migration_files_present():
    revisions = _load_revisions()
    assert len(revisions) > 40, "expected the full migration history to be discovered"


def test_exactly_one_head():
    """No revision may be left un-referenced except the single head."""
    revisions = _load_revisions()
    referenced = {down for down in revisions.values() if down is not None}
    heads = sorted(rev for rev in revisions if rev not in referenced)
    assert len(heads) == 1, f"branched migration chain — multiple heads: {heads}"


def test_exactly_one_base():
    revisions = _load_revisions()
    bases = sorted(rev for rev, down in revisions.items() if down is None)
    assert len(bases) == 1, f"multiple base revisions: {bases}"


def test_no_forked_down_revision():
    """Two revisions sharing a parent is the specific defect this guards."""
    revisions = _load_revisions()
    children: dict[str, list[str]] = {}
    for rev, down in revisions.items():
        if down is not None:
            children.setdefault(down, []).append(rev)
    forks = {parent: sorted(kids) for parent, kids in children.items() if len(kids) > 1}
    assert not forks, f"revisions sharing a parent: {forks}"


def test_every_down_revision_resolves():
    revisions = _load_revisions()
    dangling = sorted(
        f"{rev} -> {down}"
        for rev, down in revisions.items()
        if down is not None and down not in revisions
    )
    assert not dangling, f"down_revision pointing at a missing revision: {dangling}"


def test_chain_is_fully_linear_from_base_to_head():
    """Walking from the base must visit every revision exactly once."""
    revisions = _load_revisions()
    children = {down: rev for rev, down in revisions.items() if down is not None}
    base = next(rev for rev, down in revisions.items() if down is None)

    walked = [base]
    cursor = base
    while cursor in children:
        cursor = children[cursor]
        walked.append(cursor)

    assert len(walked) == len(revisions), (
        f"walk covered {len(walked)} of {len(revisions)} revisions — "
        "the chain is branched or disconnected"
    )


def test_resolution_intelligence_revision_chains_off_portfolio_registry():
    """Pins the un-branching of the ops-center resolution migration."""
    revisions = _load_revisions()
    assert revisions["052"] == "051"
    assert revisions["051"] == "049"
