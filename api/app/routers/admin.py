import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission, get_current_user
from app.models.device import Device
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.user import User
from app.services.auth import generate_invite_token, hash_password, validate_password_strength

router = APIRouter()

ALLOWED_ROLES = {"SuperAdmin", "Admin", "Manager", "User"}


# ── Schemas ──────────────────────────────────────────────────────────────────

class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    tenant_id: str
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    invite_token: Optional[str] = None
    invite_expires_at: Optional[datetime] = None
    must_change_password: bool = False
    invite_status: Optional[str] = None  # "pending" | "expired" | null

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user: "User") -> "AdminUserOut":
        out = cls.model_validate(user)
        if user.invite_token:
            if user.invite_expires_at and user.invite_expires_at < datetime.now(timezone.utc):
                out.invite_status = "expired"
            else:
                out.invite_status = "pending"
        return out


class AdminUserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str
    tenant_id: Optional[str] = None  # defaults to current user's tenant


class AdminInviteCreate(BaseModel):
    email: EmailStr
    name: str
    role: str
    tenant_id: Optional[str] = None


class AdminInviteOut(AdminUserOut):
    invite_url: Optional[str] = None


class AdminUserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    tenant_id: Optional[str] = None


# Keep backward compat schema for the old PUT endpoint (now subsumed by PATCH)
class RoleUpdate(BaseModel):
    role: str


# ── Tenant Schemas ──────────────────────────────────────────────────────────

TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class TenantOut(BaseModel):
    tenant_id: str
    name: str
    org_type: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TenantCreate(BaseModel):
    tenant_id: str
    name: str

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        v = v.strip().lower()
        if not TENANT_ID_RE.match(v):
            raise ValueError("tenant_id must be a lowercase slug (a-z, 0-9, hyphens only)")
        if len(v) > 100:
            raise ValueError("tenant_id must be 100 characters or fewer")
        return v


class TenantUpdate(BaseModel):
    name: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/users",
    response_model=list[AdminUserOut],
    dependencies=[Depends(require_permission("MANAGE_USERS"))],
)
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: Optional[str] = None,
):
    """List users. SuperAdmin sees all (with optional ?tenant_id filter). Others see own tenant."""
    q = select(User)
    if current_user.role == "SuperAdmin":
        if tenant_id:
            q = q.where(User.tenant_id == tenant_id)
    else:
        q = q.where(User.tenant_id == current_user.tenant_id)
    result = await db.execute(q.order_by(User.created_at))
    return [AdminUserOut.from_user(u) for u in result.scalars().all()]


@router.post(
    "/users/invite",
    response_model=AdminInviteOut,
    status_code=201,
    dependencies=[Depends(require_permission("MANAGE_USERS"))],
)
async def invite_user(
    body: AdminInviteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a user via invite link. Admin only."""
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Invalid role '{body.role}'. Must be one of: {', '.join(sorted(ALLOWED_ROLES))}",
        )
    # Only SuperAdmin can assign the SuperAdmin role
    if body.role == "SuperAdmin" and current_user.role != "SuperAdmin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only a SuperAdmin can assign the SuperAdmin role",
        )

    email = body.email.strip().lower()
    existing = await db.execute(
        select(User).where(func.lower(User.email) == email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists"
        )

    tenant_id = body.tenant_id or current_user.tenant_id
    token = generate_invite_token()

    user = User(
        email=email,
        name=body.name,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=body.role,
        tenant_id=tenant_id,
        is_active=False,
        invite_token=token,
        invite_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    out = AdminInviteOut.from_user(user)
    out.invite_url = f"/AuthGate?invite={token}"
    return out


@router.post(
    "/users",
    response_model=AdminUserOut,
    status_code=201,
    dependencies=[Depends(require_permission("MANAGE_USERS"))],
)
async def create_user(
    body: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new user with password. Admin only. User must change password on first login."""
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Invalid role '{body.role}'. Must be one of: {', '.join(sorted(ALLOWED_ROLES))}",
        )
    # Only SuperAdmin can assign the SuperAdmin role
    if body.role == "SuperAdmin" and current_user.role != "SuperAdmin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only a SuperAdmin can assign the SuperAdmin role",
        )

    pwd_err = validate_password_strength(body.password)
    if pwd_err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, pwd_err)

    email = body.email.strip().lower()

    existing = await db.execute(
        select(User).where(func.lower(User.email) == email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists"
        )

    tenant_id = body.tenant_id or current_user.tenant_id

    user = User(
        email=email,
        name=body.name,
        password_hash=hash_password(body.password),
        role=body.role,
        tenant_id=tenant_id,
        must_change_password=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return AdminUserOut.from_user(user)


@router.post(
    "/users/{user_id}/resend-invite",
    response_model=AdminInviteOut,
    dependencies=[Depends(require_permission("MANAGE_USERS"))],
)
async def resend_invite(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Regenerate invite token and reset expiry. Admin only."""
    q = select(User).where(User.id == user_id)
    if current_user.role != "SuperAdmin":
        q = q.where(User.tenant_id == current_user.tenant_id)
    result = await db.execute(q)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    token = generate_invite_token()
    user.invite_token = token
    user.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    user.is_active = False
    await db.commit()
    await db.refresh(user)

    out = AdminInviteOut.from_user(user)
    out.invite_url = f"/AuthGate?invite={token}"
    return out


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserOut,
    dependencies=[Depends(require_permission("MANAGE_USERS"))],
)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a user (role, is_active, password, name). Admin only."""
    q = select(User).where(User.id == user_id)
    if current_user.role != "SuperAdmin":
        q = q.where(User.tenant_id == current_user.tenant_id)
    result = await db.execute(q)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Prevent admin from disabling themselves
    if body.is_active is False and user.id == current_user.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You cannot disable your own account"
        )

    if body.role is not None:
        if body.role not in ALLOWED_ROLES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Invalid role '{body.role}'. Must be one of: {', '.join(sorted(ALLOWED_ROLES))}",
            )
        # Only SuperAdmin can assign the SuperAdmin role
        if body.role == "SuperAdmin" and current_user.role != "SuperAdmin":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Only a SuperAdmin can assign the SuperAdmin role",
            )
        user.role = body.role

    if body.is_active is not None:
        user.is_active = body.is_active

    if body.password is not None:
        pwd_err = validate_password_strength(body.password)
        if pwd_err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, pwd_err)
        user.password_hash = hash_password(body.password)

    if body.name is not None:
        user.name = body.name

    if body.email is not None:
        new_email = body.email.strip().lower()
        if new_email != user.email:
            dup = await db.execute(
                select(User).where(func.lower(User.email) == new_email)
            )
            if dup.scalar_one_or_none():
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "An account with this email already exists",
                )
            user.email = new_email

    if body.tenant_id is not None:
        if current_user.role != "SuperAdmin":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Only SuperAdmin can change tenant assignment",
            )
        # Validate target tenant exists
        t_check = await db.execute(
            select(Tenant).where(Tenant.tenant_id == body.tenant_id)
        )
        if not t_check.scalar_one_or_none():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Tenant '{body.tenant_id}' does not exist",
            )
        user.tenant_id = body.tenant_id

    await db.commit()
    await db.refresh(user)
    return AdminUserOut.from_user(user)


@router.put(
    "/users/{user_id}",
    response_model=AdminUserOut,
    dependencies=[Depends(require_permission("MANAGE_USERS"))],
)
async def put_update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full update a user (PUT alias for PATCH). Accepts same fields."""
    return await update_user(user_id, body, db, current_user)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("MANAGE_USERS"))],
)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a user. Admin only. Cannot delete yourself."""
    if user_id == current_user.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You cannot delete your own account"
        )

    q = select(User).where(User.id == user_id)
    if current_user.role != "SuperAdmin":
        q = q.where(User.tenant_id == current_user.tenant_id)
    result = await db.execute(q)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    await db.delete(user)
    await db.commit()


@router.put(
    "/users/{user_id}/role",
    response_model=AdminUserOut,
    dependencies=[Depends(require_permission("MANAGE_USERS"))],
)
async def update_user_role(
    user_id: uuid.UUID,
    body: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote/demote a user's role. Admin only. (Legacy — prefer PATCH /users/{id})"""
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Invalid role '{body.role}'. Must be one of: {', '.join(sorted(ALLOWED_ROLES))}",
        )
    # Only SuperAdmin can assign the SuperAdmin role
    if body.role == "SuperAdmin" and current_user.role != "SuperAdmin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only a SuperAdmin can assign the SuperAdmin role",
        )

    q = select(User).where(User.id == user_id)
    if current_user.role != "SuperAdmin":
        q = q.where(User.tenant_id == current_user.tenant_id)
    result = await db.execute(q)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user.role = body.role
    await db.commit()
    await db.refresh(user)
    return AdminUserOut.from_user(user)


# ── Tenant Endpoints ────────────────────────────────────────────────────────

@router.get(
    "/tenants",
    response_model=list[TenantOut],
    dependencies=[Depends(require_permission("GLOBAL_ADMIN"))],
)
async def list_tenants(db: AsyncSession = Depends(get_db)):
    """List all tenants. SuperAdmin only."""
    result = await db.execute(select(Tenant).order_by(Tenant.created_at))
    return [TenantOut.model_validate(t) for t in result.scalars().all()]


@router.get(
    "/tenants/audit",
    dependencies=[Depends(require_permission("GLOBAL_ADMIN"))],
)
async def audit_tenants(db: AsyncSession = Depends(get_db)):
    """Audit all tenants: show tenant_id, name, site count, and sample customer_names."""
    t_result = await db.execute(select(Tenant).order_by(Tenant.name))
    tenants = t_result.scalars().all()

    s_result = await db.execute(select(Site))
    sites = s_result.scalars().all()

    sites_by_tenant: dict[str, list[Site]] = {}
    for s in sites:
        sites_by_tenant.setdefault(s.tenant_id, []).append(s)

    # Also collect all distinct customer_names across all sites
    all_customer_names = sorted({
        (s.customer_name or "").strip()
        for s in sites
        if (s.customer_name or "").strip()
    })

    rows = []
    for t in tenants:
        t_sites = sites_by_tenant.get(t.tenant_id, [])
        sample_names = sorted({
            (s.customer_name or "").strip()
            for s in t_sites
            if (s.customer_name or "").strip()
        })[:5]
        sample_site_names = sorted({
            (s.site_name or "").strip()
            for s in t_sites
            if (s.site_name or "").strip()
        })[:5]
        rows.append({
            "tenant_id": t.tenant_id,
            "name": t.name,
            "site_count": len(t_sites),
            "sample_customer_names": sample_names,
            "sample_site_names": sample_site_names,
        })

    return {
        "tenants": rows,
        "total_tenants": len(tenants),
        "total_sites": len(sites),
        "all_distinct_customer_names": all_customer_names,
    }


@router.post(
    "/tenants",
    response_model=TenantOut,
    status_code=201,
    dependencies=[Depends(require_permission("GLOBAL_ADMIN"))],
)
async def create_tenant(body: TenantCreate, db: AsyncSession = Depends(get_db)):
    """Create a new tenant. SuperAdmin only."""
    existing = await db.execute(
        select(Tenant).where(Tenant.tenant_id == body.tenant_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Tenant '{body.tenant_id}' already exists",
        )

    tenant = Tenant(tenant_id=body.tenant_id, name=body.name.strip())
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return TenantOut.model_validate(tenant)


@router.patch(
    "/tenants/{tenant_id}",
    response_model=TenantOut,
    dependencies=[Depends(require_permission("GLOBAL_ADMIN"))],
)
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a tenant's name. Admin only."""
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    tenant.name = body.name.strip()
    await db.commit()
    await db.refresh(tenant)
    return TenantOut.model_validate(tenant)


@router.post(
    "/tenants/cleanup",
    dependencies=[Depends(require_permission("GLOBAL_ADMIN"))],
)
async def cleanup_tenants(
    target_tenant_id: str = "rh",
    dry_run: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete junk tenants (numeric IDs, device names, etc.) and move their sites
    back to a target tenant. Use dry_run=true to preview, dry_run=false to execute.

    A tenant is considered 'junk' if its tenant_id:
      - is purely numeric (e.g. '849')
      - looks like a device/model name (e.g. 'facp-1', 'csa-200')
      - is very short (1-2 chars) unless it's a known slug
    """
    t_result = await db.execute(select(Tenant))
    tenants = t_result.scalars().all()

    # Validate target tenant exists
    target = None
    for t in tenants:
        if t.tenant_id == target_tenant_id:
            target = t
            break
    if not target:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Target tenant '{target_tenant_id}' does not exist",
        )

    # Patterns that indicate junk tenant IDs
    device_patterns = re.compile(
        r"^(facp|csa|das|panel|sensor|unit|device|model|serial|sim|imei|iccid|msisdn)"
        r"[-_]?\d*$",
        re.IGNORECASE,
    )

    def _is_junk_tenant(tid: str) -> bool:
        cleaned = tid.replace("-", "").replace("_", "")
        if cleaned.isdigit():
            return True
        if device_patterns.match(tid):
            return True
        if len(tid) <= 2 and not tid.isalpha():
            return True
        return False

    junk_tenants = [t for t in tenants if _is_junk_tenant(t.tenant_id) and t.tenant_id != target_tenant_id]

    # Load sites and devices in junk tenants
    junk_ids = {t.tenant_id for t in junk_tenants}
    s_result = await db.execute(select(Site).where(Site.tenant_id.in_(junk_ids)))
    junk_sites = s_result.scalars().all()
    d_result = await db.execute(select(Device).where(Device.tenant_id.in_(junk_ids)))
    junk_devices = d_result.scalars().all()

    preview = {
        "dry_run": dry_run,
        "target_tenant": target_tenant_id,
        "junk_tenants": [{"tenant_id": t.tenant_id, "name": t.name} for t in junk_tenants],
        "junk_tenant_count": len(junk_tenants),
        "sites_to_move": len(junk_sites),
        "devices_to_move": len(junk_devices),
    }

    if dry_run:
        return preview

    # Move sites and devices to target
    for site in junk_sites:
        site.tenant_id = target_tenant_id
    for device in junk_devices:
        device.tenant_id = target_tenant_id

    await db.flush()

    # Delete junk tenants (now empty)
    for t in junk_tenants:
        await db.delete(t)

    await db.commit()

    preview["status"] = "completed"
    return preview


@router.post(
    "/reset-imported-data",
    dependencies=[Depends(require_permission("GLOBAL_ADMIN"))],
)
async def reset_imported_data(
    keep_tenant_id: str = "rh",
    dry_run: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Wipe ALL imported sites, devices, and auto-provisioned tenants.
    Keeps the specified tenant (SuperAdmin's home tenant) and its users.
    Use dry_run=true to preview, dry_run=false to execute.
    """
    from sqlalchemy import text

    # Count what we'll delete
    site_count = await db.scalar(select(func.count()).select_from(Site)) or 0
    device_count = await db.scalar(select(func.count()).select_from(Device)) or 0

    tenant_count = await db.scalar(
        select(func.count()).select_from(Tenant).where(Tenant.tenant_id != keep_tenant_id)
    ) or 0

    preview = {
        "dry_run": dry_run,
        "keep_tenant": keep_tenant_id,
        "sites_to_delete": site_count,
        "devices_to_delete": device_count,
        "tenants_to_delete": tenant_count,
    }

    if dry_run:
        return preview

    # Disable FK checks, wipe data tables, re-enable.
    # This is the only reliable way to clear interlinked tables fast.
    await db.execute(text("SET session_replication_role = 'replica'"))

    # Delete from all data tables (order doesn't matter with FKs disabled)
    data_tables = [
        "device_sim_assignments", "sim_events", "sim_usage_daily", "sims",
        "site_vendor_assignments", "service_contracts", "verification_tasks",
        "command_activities", "command_telemetry", "incidents",
        "notification_rules", "notifications", "e911_change_log",
        "telemetry_events", "action_audits", "recordings", "events",
        "lines", "outbound_webhooks", "automation_rules", "escalation_rules",
        "devices", "sites", "vendors", "external_subscription_maps",
        "external_customer_maps", "subscriptions", "customers",
        "integration_statuses", "integrations", "providers",
    ]
    for table in data_tables:
        try:
            await db.execute(text(f"DELETE FROM {table}"))
        except Exception:
            pass  # table may not exist

    # Delete tenants except the keeper
    try:
        await db.execute(text(
            "DELETE FROM tenants WHERE tenant_id != :keep"
        ).bindparams(keep=keep_tenant_id))
    except Exception:
        pass

    # Re-enable FK checks
    await db.execute(text("SET session_replication_role = 'origin'"))

    await db.commit()
    preview["status"] = "completed"
    return preview


# ── Auto-Provision Tenants from Imported Sites ─────────────────────────────

def _slugify(name: str) -> str:
    """Convert a customer name to a tenant slug: lowercase, alphanumeric + hyphens."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    slug = slug.strip("-")
    return slug[:100] if slug else ""


# Patterns that look like device/equipment names, not real companies
_DEVICE_NAME_RE = re.compile(
    r"^(facp|csa|das|panel|sensor|unit|device|model|serial|sim|gateway|router|switch|ap|radio)"
    r"[-_\s]?\d+",
    re.IGNORECASE,
)


def _is_valid_customer_name(name: str) -> bool:
    """Return True if name looks like a real company name, not a numeric ID or device label."""
    stripped = name.strip()
    if not stripped:
        return False
    # Pure numeric
    cleaned = stripped.replace("-", "").replace("_", "").replace(" ", "")
    if cleaned.isdigit():
        return False
    # Device/equipment pattern
    if _DEVICE_NAME_RE.match(stripped):
        return False
    # Too short to be a real name (single char or 2-letter non-word)
    if len(stripped) <= 2 and not stripped.isalpha():
        return False
    return True


class TenantGroupOut(BaseModel):
    customer_name: str
    proposed_tenant_id: str
    proposed_display_name: str
    site_count: int
    device_count: int
    existing_tenant: Optional[str] = None  # set if tenant already exists


class AutoProvisionPreview(BaseModel):
    total_sites: int
    unique_customers: int
    groups: list[TenantGroupOut]
    tenants_to_create: int
    tenants_already_exist: int


class AutoProvisionCommit(BaseModel):
    commit: bool = True
    source_tenant_id: Optional[str] = None  # limit to sites in a specific tenant


class AutoProvisionResult(BaseModel):
    tenants_created: int
    sites_reassigned: int
    devices_reassigned: int
    skipped_empty_name: int
    details: list[dict]


@router.post(
    "/auto-provision/preview",
    response_model=AutoProvisionPreview,
    dependencies=[Depends(require_permission("GLOBAL_ADMIN"))],
)
async def auto_provision_preview(
    source_tenant_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Preview tenant auto-provisioning from customer_name groupings. SuperAdmin only."""
    q = select(Site)
    if source_tenant_id:
        q = q.where(Site.tenant_id == source_tenant_id)
    result = await db.execute(q)
    sites = result.scalars().all()

    # Load devices for counting
    dq = select(Device)
    if source_tenant_id:
        dq = dq.where(Device.tenant_id == source_tenant_id)
    dev_result = await db.execute(dq)
    all_devices = dev_result.scalars().all()
    devices_by_site: dict[str, int] = {}
    for d in all_devices:
        if d.site_id:
            devices_by_site[d.site_id] = devices_by_site.get(d.site_id, 0) + 1

    # Load existing tenants
    t_result = await db.execute(select(Tenant))
    existing_tenants = {t.tenant_id: t for t in t_result.scalars().all()}

    # Group sites by customer_name (skip junk names)
    groups: dict[str, list[Site]] = {}
    skipped_junk = 0
    for site in sites:
        name = (site.customer_name or "").strip()
        if not name:
            continue
        if not _is_valid_customer_name(name):
            skipped_junk += 1
            continue
        groups.setdefault(name, []).append(site)

    group_list = []
    tenants_to_create = 0
    tenants_already_exist = 0
    for cust_name, cust_sites in sorted(groups.items(), key=lambda x: -len(x[1])):
        slug = _slugify(cust_name)
        if not slug:
            continue
        dev_count = sum(devices_by_site.get(s.site_id, 0) for s in cust_sites)
        existing = existing_tenants.get(slug)
        if existing:
            tenants_already_exist += 1
        else:
            tenants_to_create += 1
        group_list.append(TenantGroupOut(
            customer_name=cust_name,
            proposed_tenant_id=slug,
            proposed_display_name=cust_name,
            site_count=len(cust_sites),
            device_count=dev_count,
            existing_tenant=slug if existing else None,
        ))

    return AutoProvisionPreview(
        total_sites=len(sites),
        unique_customers=len(groups),
        groups=group_list,
        tenants_to_create=tenants_to_create,
        tenants_already_exist=tenants_already_exist,
    )


@router.post(
    "/auto-provision/commit",
    response_model=AutoProvisionResult,
    dependencies=[Depends(require_permission("GLOBAL_ADMIN"))],
)
async def auto_provision_commit(
    body: AutoProvisionCommit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create tenants from customer_name groupings and reassign sites + devices. SuperAdmin only."""
    q = select(Site)
    if body.source_tenant_id:
        q = q.where(Site.tenant_id == body.source_tenant_id)
    result = await db.execute(q)
    sites = result.scalars().all()

    # Load existing tenants
    t_result = await db.execute(select(Tenant))
    existing_tenants = {t.tenant_id for t in t_result.scalars().all()}

    # Batch-load ALL devices upfront to avoid N+1 queries
    dev_result = await db.execute(select(Device))
    all_devices = dev_result.scalars().all()
    devices_by_site: dict[str, list[Device]] = {}
    for d in all_devices:
        if d.site_id:
            devices_by_site.setdefault(d.site_id, []).append(d)

    # Group sites by customer_name (skip junk names)
    groups: dict[str, list[Site]] = {}
    skipped = 0
    for site in sites:
        name = (site.customer_name or "").strip()
        if not name or not _is_valid_customer_name(name):
            skipped += 1
            continue
        groups.setdefault(name, []).append(site)

    # Phase 1: Create all missing tenants first, then flush so FKs are valid
    tenants_created = 0
    for cust_name in groups:
        slug = _slugify(cust_name)
        if not slug or slug in existing_tenants:
            continue
        tenant = Tenant(tenant_id=slug, name=cust_name)
        db.add(tenant)
        existing_tenants.add(slug)
        tenants_created += 1

    if tenants_created > 0:
        await db.flush()  # make tenant rows visible for FK constraints

    # Phase 2: Reassign sites and devices
    sites_reassigned = 0
    devices_reassigned = 0
    details = []

    for cust_name, cust_sites in sorted(groups.items(), key=lambda x: -len(x[1])):
        slug = _slugify(cust_name)
        if not slug:
            skipped += len(cust_sites)
            continue

        # Reassign sites
        for site in cust_sites:
            if site.tenant_id != slug:
                site.tenant_id = slug
                sites_reassigned += 1

        # Reassign devices using pre-loaded data
        dev_count = 0
        for site in cust_sites:
            for d in devices_by_site.get(site.site_id, []):
                if d.tenant_id != slug:
                    d.tenant_id = slug
                    dev_count += 1
                    devices_reassigned += 1

        details.append({
            "customer_name": cust_name,
            "tenant_id": slug,
            "sites": len(cust_sites),
            "devices_moved": dev_count,
        })

    await db.commit()

    return AutoProvisionResult(
        tenants_created=tenants_created,
        sites_reassigned=sites_reassigned,
        devices_reassigned=devices_reassigned,
        skipped_empty_name=skipped,
        details=details,
    )
