"""Pydantic schemas for the subscriber / line-centric import engine."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Preview ────────────────────────────────────────────────────────

class SubscriberRowPreview(BaseModel):
    row: int
    customer_name: str | None = None
    site_name: str | None = None
    device_id: str | None = None
    msisdn: str | None = None
    sim_iccid: str | None = None
    tenant_action: str  # create | match | skip
    site_action: str
    device_action: str
    line_action: str  # create | update | duplicate | skip
    status: str  # ok | warning | error
    errors: list[str] = []
    warnings: list[str] = []


class SubscriberPreviewSummary(BaseModel):
    total_rows: int = 0
    new_tenants: int = 0
    matched_tenants: int = 0
    new_sites: int = 0
    matched_sites: int = 0
    new_devices: int = 0
    matched_devices: int = 0
    new_lines: int = 0
    updated_lines: int = 0
    duplicate_rows: int = 0
    error_rows: int = 0
    warning_rows: int = 0


class SubscriberPreviewResponse(BaseModel):
    total_rows: int
    summary: SubscriberPreviewSummary
    rows: list[SubscriberRowPreview]
    has_errors: bool


# ── Commit ─────────────────────────────────────────────────────────

class SubscriberCommitSummary(BaseModel):
    tenants_created: int = 0
    tenants_matched: int = 0
    sites_created: int = 0
    sites_matched: int = 0
    devices_created: int = 0
    devices_matched: int = 0
    lines_created: int = 0
    lines_updated: int = 0
    lines_matched: int = 0
    rows_created: int = 0
    rows_updated: int = 0
    rows_matched: int = 0
    rows_failed: int = 0
    rows_flagged: int = 0


class SubscriberCommitResponse(BaseModel):
    batch_id: str | None
    summary: SubscriberCommitSummary
    errors: list[str]
    total_rows: int


# ── Verification ───────────────────────────────────────────────────

class CustomerVerificationSummary(BaseModel):
    customer_id: int
    customer_name: str
    customer_number: str | None = None
    sites: int
    devices: int
    lines: int
    health_score: int
    unresolved_issues: int
    reconciliation_status: str | None = None


class LineDetail(BaseModel):
    line_id: str
    did: str | None = None
    sim_iccid: str | None = None
    carrier: str | None = None
    line_type: str | None = None
    status: str | None = None
    reconciliation_status: str | None = None
    qb_description: str | None = None


class DeviceDetail(BaseModel):
    device_id: str
    device_type: str | None = None
    imei: str | None = None
    iccid: str | None = None
    msisdn: str | None = None
    carrier: str | None = None
    status: str | None = None
    reconciliation_status: str | None = None
    lines: list[LineDetail] = []
    warnings: list[str] = []


class OrphanLine(BaseModel):
    line_id: str
    did: str | None = None
    sim_iccid: str | None = None
    carrier: str | None = None
    reconciliation_status: str | None = None


class SiteVerificationDetail(BaseModel):
    site_id: str
    site_name: str
    customer_name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    status: str | None = None
    reconciliation_status: str | None = None
    devices: list[DeviceDetail] = []
    orphan_lines: list[OrphanLine] = []


# ── Batch history ──────────────────────────────────────────────────

class ImportBatchSummary(BaseModel):
    batch_id: str
    file_name: str | None = None
    status: str
    total_rows: int | None = None
    rows_created: int | None = None
    rows_updated: int | None = None
    rows_failed: int | None = None
    tenants_created: int | None = None
    sites_created: int | None = None
    devices_created: int | None = None
    lines_created: int | None = None
    created_by: str | None = None
    committed_at: str | None = None
    created_at: str | None = None


class ImportRowDetail(BaseModel):
    row_number: int
    status: str
    action_summary: str | None = None
    tenant_action: str | None = None
    site_action: str | None = None
    device_action: str | None = None
    line_action: str | None = None
    site_id_resolved: str | None = None
    device_id_resolved: str | None = None
    line_id_resolved: str | None = None
    reconciliation_status: str | None = None
    errors: list[str] = []
    warnings: list[str] = []


# ── Correction requests ────────────────────────────────────────────

class ReassignLineRequest(BaseModel):
    line_id: str
    new_device_id: str


class ReassignDeviceRequest(BaseModel):
    device_id: str
    new_site_id: str


class MergeSitesRequest(BaseModel):
    keep_site_id: str
    merge_site_id: str


class MergeDevicesRequest(BaseModel):
    keep_device_id: str
    merge_device_id: str


class UpdateReconciliationRequest(BaseModel):
    entity_type: str  # line | device | site
    entity_id: str
    status: str  # clean | needs_review | incomplete | duplicate_suspected | imported_unverified | verified


class UpdateLineRequest(BaseModel):
    did: str | None = None
    sim_iccid: str | None = None
    carrier: str | None = None
    line_type: str | None = None
    qb_description: str | None = None
    notes: str | None = None
