"""Canonical Life-Safety Service & Connection reconciliation (DECISIONS D-023).

    vocab      closed vocabularies (confidence / approval / lifecycle / types)
    normalize  identifier + label normalisation, masking, label classification
    decisions  operator-decision ledger: validation, keys, supersession
    engine     PURE projection: snapshot -> assets / services / connections /
               findings / summaries (no DB, no I/O)
    loader     read-only snapshot builder (DB SELECTs + live read-only Zoho GETs)
    writer     persists a projection - only under an explicit ``--apply``
    report     plain-text dry-run report (masked)

Nothing customer-facing reads the canonical tables in PR #186a; the customer
read model is PR #186b behind ``FEATURE_CANONICAL_SERVICE_MODEL``.
"""
