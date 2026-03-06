"""Pydantic schemas for site-centric CSV import engine."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ImportRowValidation(BaseModel):
    row: int
    site_name: str | None = None
    site_code: str | None = None
    system_type: str | None = None
    device_serial: str | None = None
    action: str  # "create_site", "attach_to_site", "create_device", "skip"
    errors: list[str] = []
    warnings: list[str] = []


class ImportPreviewSummary(BaseModel):
    total_rows: int
    sites_to_create: int
    sites_to_attach: int
    systems_to_create: int
    devices_to_create: int
    vendors_to_create: int
    vendors_to_match: int
    verifications_to_create: int
    rows: list[ImportRowValidation]
    has_errors: bool


class ImportCommitResult(BaseModel):
    total_rows: int
    sites_created: int
    sites_attached: int
    devices_created: int
    vendors_created: int
    vendor_assignments_created: int
    verifications_created: int
    errors: list[str]
