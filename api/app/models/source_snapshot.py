"""Operational source snapshots - immutable evidence (DECISIONS D-024).

A snapshot is ONE imported export file (NAPCO RadioList, T-Mobile/Infatrac,
Verizon ThingSpace, Red Pocket) for ONE tenant.  It is evidence, never a
mutable mirror of the source system:

  * written once (explicit ``--apply``), never updated, never deleted;
  * de-duplicated by the file's SHA-256 per (tenant, source);
  * each record keeps the RAW source status beside the interpreted lifecycle
    and the versioned rule that produced it;
  * only rows attributed to the tenant are stored - another customer's row is
    never persisted into this tenant;
  * attributes are an allow-listed, sanitised subset of the source columns.

Nothing reads these tables to change canonical services, E911, the registry
or operator decisions in PR #187; the lifecycle reconciliation that consumes
them is PR #188.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    source_system: Mapped[str] = mapped_column(String(20), nullable=False)   # NAPCO / T_MOBILE / ...
    source_label: Mapped[str] = mapped_column(String(120), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_basename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_name: Mapped[str] = mapped_column(String(60), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status_map_version: Mapped[str] = mapped_column(String(60), nullable=False)
    attribution_rule_version: Mapped[str] = mapped_column(String(60), nullable=False)
    source_effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_at_basis: Mapped[str] = mapped_column(String(20), nullable=False)  # OPERATOR/FILENAME/UNKNOWN
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    imported_by: Mapped[str] = mapped_column(String(255), nullable=False)
    row_count_total: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count_attributed: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count_excluded: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count_ambiguous: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count_invalid: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # JSON, masked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "source_system", "file_sha256", name="uq_source_snapshot_sha"),
        Index("ix_source_snapshots_tenant_source", "tenant_id", "source_system"),
    )


class SourceSnapshotRecord(Base):
    __tablename__ = "source_snapshot_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    source_system: Mapped[str] = mapped_column(String(20), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_record_key: Mapped[str] = mapped_column(String(120), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(20), nullable=False)
    normalized_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    msisdn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    iccid: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    imei: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    napco_radio: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    source_status_raw: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    lifecycle_interpretation: Mapped[str] = mapped_column(String(20), nullable=False)
    interpretation_rule: Mapped[str] = mapped_column(String(120), nullable=False)
    activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    location_hint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attribution_basis: Mapped[str] = mapped_column(String(60), nullable=False)
    attribution_confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attributes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # JSON, allow-listed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("snapshot_id", "row_number", name="uq_snapshot_record_row"),
        Index("ix_snapshot_records_identifier", "tenant_id", "source_system",
              "normalized_identifier"),
    )
