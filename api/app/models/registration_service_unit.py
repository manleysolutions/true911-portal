"""A requested service unit at a registration location.

Examples: an elevator emergency phone, a fire alarm communicator.
Materialises to a `service_units` row at conversion time.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RegistrationServiceUnit(Base):
    __tablename__ = "registration_service_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"),
        index=True,
    )
    registration_location_id: Mapped[int] = mapped_column(
        ForeignKey("registration_locations.id", ondelete="CASCADE"),
        index=True,
    )

    unit_label: Mapped[str] = mapped_column(String(255))
    unit_type: Mapped[str] = mapped_column(String(50))
    # values mirror ServiceUnit.unit_type:
    #   elevator_phone | fire_alarm | emergency_call_station | fax_line | voice_line | other

    phone_number_existing: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hardware_model_request: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    carrier_request: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    install_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # new | modernization | existing

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    materialized_service_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("service_units.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
