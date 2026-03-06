from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# -- Site Templates --

class SiteTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    building_type: str
    systems_json: Optional[str] = None
    verification_tasks_json: Optional[str] = None
    monitoring_rules_json: Optional[str] = None
    readiness_weights_json: Optional[str] = None
    is_global: bool = False


class SiteTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    building_type: Optional[str] = None
    systems_json: Optional[str] = None
    verification_tasks_json: Optional[str] = None
    monitoring_rules_json: Optional[str] = None
    readiness_weights_json: Optional[str] = None
    is_global: Optional[bool] = None


class SiteTemplateOut(BaseModel):
    id: int
    tenant_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    building_type: str
    systems_json: Optional[str] = None
    verification_tasks_json: Optional[str] = None
    monitoring_rules_json: Optional[str] = None
    readiness_weights_json: Optional[str] = None
    is_global: bool
    created_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# -- Service Contracts --

class ServiceContractCreate(BaseModel):
    vendor_id: int
    site_id: Optional[str] = None
    contract_type: str
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sla_response_minutes: Optional[int] = None
    sla_resolution_hours: Optional[int] = None
    notes: Optional[str] = None


class ServiceContractUpdate(BaseModel):
    contract_type: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sla_response_minutes: Optional[int] = None
    sla_resolution_hours: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ServiceContractOut(BaseModel):
    id: int
    tenant_id: str
    vendor_id: int
    site_id: Optional[str] = None
    contract_type: str
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sla_response_minutes: Optional[int] = None
    sla_resolution_hours: Optional[int] = None
    status: str
    notes: Optional[str] = None
    vendor_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# -- Outbound Webhooks --

class OutboundWebhookCreate(BaseModel):
    name: str
    url: str
    secret: Optional[str] = None
    events: str  # JSON array, e.g. '["incident.created","incident.resolved"]'
    enabled: bool = True


class OutboundWebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[str] = None
    enabled: Optional[bool] = None


class OutboundWebhookOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    url: str
    events: str
    enabled: bool
    last_triggered_at: Optional[datetime] = None
    last_status_code: Optional[int] = None
    failure_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# -- Bulk Import --

class BulkImportResult(BaseModel):
    total_rows: int
    created: int
    skipped: int
    errors: list[str]


# -- Org / Tenant extensions --

class TenantOrgUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    org_type: Optional[str] = None
    parent_tenant_id: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    settings_json: Optional[str] = None


class TenantOrgOut(BaseModel):
    tenant_id: str
    name: str
    org_type: str
    parent_tenant_id: Optional[str] = None
    display_name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
