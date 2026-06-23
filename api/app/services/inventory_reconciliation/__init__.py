"""Inventory Reconciliation Framework (EPIC-GEN-003).

Customer-agnostic, vendor-agnostic, READ-ONLY engine that compares an external
carrier/vendor inventory (via a pluggable adapter) against True911 inventory and
emits a per-record reconciliation. No DB writes, no feature flags, no production
mutation. Reusable for any customer (RH, R&R, Benson, Integrity, USPS, ...) and
any future vendor adapter.

Layout:
  models.py            canonical VendorRecord / True911Item / ReconRow / Result
  normalize.py         ICCID / radio / name normalization + site similarity
  engine.py            reconcile() — pure matching + classification + summary
  adapters/            vendor adapters (base protocol + registry); napco first
  export.py            CSV + JSON writers
  inventory.py         read-only True911 inventory loader (DB glue)
"""
