"""Operational source snapshots (DECISIONS D-024).

    status       versioned raw-status -> lifecycle maps (unknown -> UNKNOWN)
    reader       CSV / XLSX table reader (header detection, sheet selection)
    adapters     NAPCO / T_MOBILE / VERIZON / RED_POCKET parsers (versioned)
    attribution  tenant attribution: exact identifier match or an explicit
                 tenant-profile label rule; ambiguity is never attributed
    importer     dry-run plan + immutable ``--apply`` (SHA-256 de-duplicated)
    freshness    inventory-certification freshness of a snapshot

Snapshots are EVIDENCE.  Importing never writes a source system and never
changes canonical services, E911, the registry or operator decisions.
"""
