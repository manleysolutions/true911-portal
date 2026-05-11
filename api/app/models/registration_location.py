"""A single physical location captured during a registration.

Materialises to a `sites` row at conversion time; `materialized_site_id`
links the staged record to the production row once that happens.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RegistrationLocation(Base):
    __tablename__ = "registration_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"),
        index=True,
    )

    location_label: Mapped[str] = mapped_column(String(255))
    street: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zip: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    poc_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    poc_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    poc_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    dispatchable_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    access_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    materialized_site_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sites.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
