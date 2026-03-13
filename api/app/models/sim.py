from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Sim(Base):
    """SIM card inventory — tracks ICCID, MSISDN, IMSI and lifecycle state.

    SIMs land here via carrier sync or manual entry.  They can be unassigned
    (inventory pool) or assigned to a site / device / both.
    """
    __tablename__ = "sims"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)

    # ── Identity ─────────────────────────────────────────────────
    iccid: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    msisdn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    imsi: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    imei: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    carrier: Mapped[str] = mapped_column(String(50))  # verizon, tmobile, att, telnyx, teal

    # ── Lifecycle ────────────────────────────────────────────────
    # inventory | assigned | active | suspended | deactivated | error
    status: Mapped[str] = mapped_column(String(30), default="inventory")
    activation_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    network_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # ── Plan / Config ────────────────────────────────────────────
    plan: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    apn: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Assignment ───────────────────────────────────────────────
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # ── Provenance ───────────────────────────────────────────────
    provider_sim_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    data_source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="manual")  # manual | carrier_sync
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Inferred Location (from carrier, NOT E911-valid) ─────────
    inferred_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inferred_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inferred_location_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # verizon_api, tmobile_api, etc.

    # ── Metadata ─────────────────────────────────────────────────
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
