from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# -- Vendors --

class VendorCreate(BaseModel):
    name: str
    vendor_type: str = "general"
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    specialties_json: Optional[str] = None
    notes: Optional[str] = None


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    vendor_type: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    specialties_json: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class VendorOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    vendor_type: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    specialties_json: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# -- Site Vendor Assignments --

class SiteVendorAssignmentCreate(BaseModel):
    site_id: str
    vendor_id: int
    system_category: str
    is_primary: bool = True
    notes: Optional[str] = None


class SiteVendorAssignmentOut(BaseModel):
    id: int
    site_id: str
    vendor_id: int
    system_category: str
    is_primary: bool
    notes: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_contact_name: Optional[str] = None
    vendor_contact_phone: Optional[str] = None
    vendor_contact_email: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# -- Verification Tasks --

class VerificationTaskCreate(BaseModel):
    site_id: str
    task_type: str
    title: str
    description: Optional[str] = None
    system_category: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    assigned_vendor_id: Optional[int] = None


class VerificationTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    assigned_vendor_id: Optional[int] = None
    status: Optional[str] = None


class VerificationTaskComplete(BaseModel):
    result: str = "pass"
    evidence_notes: Optional[str] = None


class VerificationTaskOut(BaseModel):
    id: int
    tenant_id: str
    site_id: str
    task_type: str
    title: str
    description: Optional[str] = None
    system_category: Optional[str] = None
    status: str
    priority: str
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_vendor_id: Optional[int] = None
    evidence_notes: Optional[str] = None
    result: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    is_overdue: bool = False

    model_config = {"from_attributes": True}


# -- Automation Rules --

class AutomationRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_type: str
    condition_json: str
    action_type: str
    action_config_json: Optional[str] = None
    enabled: bool = True


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[str] = None
    condition_json: Optional[str] = None
    action_type: Optional[str] = None
    action_config_json: Optional[str] = None
    enabled: Optional[bool] = None


class AutomationRuleOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    description: Optional[str] = None
    trigger_type: str
    condition_json: str
    action_type: str
    action_config_json: Optional[str] = None
    enabled: bool
    last_evaluated_at: Optional[datetime] = None
    last_fired_at: Optional[datetime] = None
    fire_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# -- Digest / Report payloads --

class SiteCommandSummary(BaseModel):
    site_id: str
    site_name: str
    status: str
    readiness_score: int
    risk_label: str
    active_incidents: int
    critical_incidents: int
    escalated_incidents: int
    stale_devices: int
    total_devices: int
    overdue_tasks: int
    total_tasks: int
    vendor_count: int
    last_activity: Optional[str] = None
