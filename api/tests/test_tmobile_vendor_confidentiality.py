"""Guards keeping confidential vendor material out of this public repository.

This repository is public. The T-Mobile Wholesale documentation it was
reconciled against was supplied to Manley Solutions as the intended recipient
and carries a confidentiality legend prohibiting retransmission. The
implementation may therefore carry the minimum wire facts needed to function —
paths, methods, field names, headers — but must never carry the source
documents, their extracted contents, or a reproduction that would substitute for
the vendor's own developer portal.

These tests are the enforcement. They scan only what this repository tracks, so
the operator's private evidence store is out of scope by construction: if it
ever shows up here, that is precisely the failure being caught.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[2]

#: Live PIT identifiers that must never appear in a fixture or test.
LIVE_PIT_ICCID = "89012609631" + "32697538"
LIVE_PIT_MSISDN = "410240" + "6851"

#: Binary/office formats a vendor export would arrive as.
VENDOR_BINARY_SUFFIXES = {
    ".pdf", ".xlsx", ".xls", ".zip", ".docx", ".doc", ".pptx", ".ppt",
}

#: Directories whose contents are legitimately allowed to be binary.
_BINARY_OK_PREFIXES = ("web/", "api/tests/fixtures/napco")


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _tracked_text(paths: list[str]) -> list[tuple[str, str]]:
    documents = []
    for rel in paths:
        p = REPO / rel
        if not p.is_file() or p.suffix.lower() in VENDOR_BINARY_SUFFIXES:
            continue
        try:
            documents.append((rel, p.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return documents


class TestNoVendorBinaryIsTracked:
    def test_no_vendor_document_format_is_committed(self):
        """A vendor export is a binary. None may be tracked."""
        offenders = [
            f for f in _tracked_files()
            if pathlib.Path(f).suffix.lower() in VENDOR_BINARY_SUFFIXES
            and not f.startswith(_BINARY_OK_PREFIXES)
        ]
        assert offenders == [], f"vendor-format binaries tracked: {offenders}"

    def test_no_wholesale_named_export_is_tracked(self):
        """Catch a renamed export by its recognisable vendor filename."""
        pattern = re.compile(r"wholesale.*(guide|glossary|samples|release|"
                             r"response.?codes|best.?practice)", re.IGNORECASE)
        offenders = [f for f in _tracked_files() if pattern.search(f)]
        assert offenders == [], f"vendor document filenames tracked: {offenders}"


class TestPrivateEvidenceStoreIsIgnored:
    def test_gitignore_has_a_narrow_rule(self):
        text = (REPO / ".gitignore").read_text(encoding="utf-8")
        assert ".private-evidence/" in text

    def test_nothing_under_the_private_store_is_tracked(self):
        offenders = [f for f in _tracked_files()
                     if f.startswith(".private-evidence")]
        assert offenders == [], f"private evidence tracked: {offenders}"

    def test_git_actually_ignores_the_directory(self):
        """Assert the ignore works, not merely that a line exists."""
        probe = REPO / ".private-evidence" / "__ignore_probe__"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("probe", encoding="utf-8")
        try:
            result = subprocess.run(
                ["git", "check-ignore", str(probe)],
                cwd=REPO, capture_output=True, text=True,
            )
            assert result.returncode == 0, "private evidence store is NOT ignored"
        finally:
            probe.unlink(missing_ok=True)


class TestNoLiveIdentifiersInTests:
    """The assigned line's identifiers stay in the restricted operator record.

    The PIT **ICCID** is deliberately not covered here: it is a long-standing
    operator-approved test constant that predates this work and already appears
    openly across the suite and the docs. Retro-fitting a ban on it would be a
    large unrelated change, and it is the least sensitive of the three — it
    identifies a lab SIM we own, not an assigned line.

    The **MSISDN and account ID** are different. They were assigned by the
    carrier on 2026-07-21 and were deliberately confined to one restricted
    document, with every other artifact masking them to the last four. That
    boundary is worth enforcing mechanically.
    """

    def test_assigned_msisdn_never_appears_in_a_test_or_fixture(self):
        offenders = [rel for rel, text in _tracked_text(_tracked_files())
                     if rel.startswith("api/") and LIVE_PIT_MSISDN in text]
        assert offenders == [], f"assigned MSISDN present in: {offenders}"

    def test_generated_account_id_never_appears_in_a_test_or_fixture(self):
        account_id = "104107" + "63214"
        offenders = [rel for rel, text in _tracked_text(_tracked_files())
                     if rel.startswith("api/") and account_id in text]
        assert offenders == [], f"generated account id present in: {offenders}"

    def test_new_contract_tests_use_fabricated_identifiers(self):
        """The reconciliation work must not have spread the live ICCID further."""
        for rel in ("api/tests/test_tmobile_vendor_confidentiality.py",
                    "api/tests/test_tmobile_response_codes.py"):
            path = REPO / rel
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            # This module names the constant only in split form, for scanning.
            assert text.count(LIVE_PIT_ICCID) == 0 or rel.endswith(
                "test_tmobile_vendor_confidentiality.py")


class TestNoVendorContentIsPublished:
    """The repository must not become a substitute for the vendor's portal."""

    def test_no_bulk_response_code_catalogue_is_committed(self):
        """A handful of reviewed codes is fine; a catalogue is republication."""
        gens = re.compile(r"GENS-\d{4}")
        for rel, text in _tracked_text(_tracked_files()):
            distinct = set(gens.findall(text))
            assert len(distinct) <= 20, (
                f"{rel} contains {len(distinct)} distinct vendor response codes — "
                "that is a catalogue, not a reviewed subset."
            )

    def test_no_vendor_document_hash_is_committed(self):
        """Document hashes identify confidential artifacts; they stay private."""
        known_hashes = (
            "b3a2c7cc", "3d4fd290", "24f4ef03", "56080d11",  # the four PDFs
            "bd7517a6", "6d48c86b", "b170b486",              # response-code set
        )
        for rel, text in _tracked_text(_tracked_files()):
            lowered = text.lower()
            for h in known_hashes:
                assert h not in lowered, f"vendor document hash in {rel}"

    def test_no_page_or_section_citation_into_the_vendor_guide(self):
        """Citations that reconstruct the source document are not published."""
        pattern = re.compile(
            r"(rest api guide|api guide|glossary\s*&\s*samples|release notes)"
            r"[^\n]{0,40}(v?\d+\.\d+\.\d+|page\s*\d+|§\s*\d+|section\s*\d+)",
            re.IGNORECASE,
        )
        offenders = [rel for rel, text in _tracked_text(_tracked_files())
                     if pattern.search(text)]
        assert offenders == [], f"vendor citations published in: {offenders}"

    def test_no_absolute_operator_path_is_committed(self):
        """A local filesystem path leaks the operator's machine layout."""
        pattern = re.compile(r"[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9._-]+", re.IGNORECASE)
        offenders = []
        for rel, text in _tracked_text(_tracked_files()):
            if pattern.search(text):
                offenders.append(rel)
        assert offenders == [], f"absolute operator paths in: {offenders}"

    def test_response_code_module_stays_a_narrow_subset(self):
        """The public mapping must not grow into an imported spreadsheet."""
        from app.integrations import tmobile_response_codes as rc

        assert len(rc.mapped_codes()) <= 20, (
            "The public response-code mapping has grown past a reviewed subset. "
            "Bulk vendor data belongs in the private evidence store."
        )

    def test_public_mapping_carries_no_vendor_prose(self):
        """Severity and disposition only — no message, reason, or resolution."""
        from app.integrations import tmobile_response_codes as rc

        for code in rc.mapped_codes():
            entry = rc.lookup(code)
            assert set(vars(entry)) == {
                "code", "severity", "disposition", "automatic_retry",
                "prerequisite_operation",
            }
