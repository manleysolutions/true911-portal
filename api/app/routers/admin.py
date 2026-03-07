import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func, select
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


# ── Auto-Provision Tenants from Imported Sites ─────────────────────────────

def _slugify(name: str) -> str:
    """Convert a customer name to a tenant slug: lowercase, alphanumeric + hyphens."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    slug = slug.strip("-")
    return slug[:100] if slug else ""


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

    # Group sites by customer_name
    groups: dict[str, list[Site]] = {}
    for site in sites:
        name = (site.customer_name or "").strip()
        if not name:
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

    # Group sites by customer_name
    groups: dict[str, list[Site]] = {}
    skipped = 0
    for site in sites:
        name = (site.customer_name or "").strip()
        if not name:
            skipped += 1
            continue
        groups.setdefault(name, []).append(site)

    tenants_created = 0
    sites_reassigned = 0
    devices_reassigned = 0
    details = []

    for cust_name, cust_sites in sorted(groups.items(), key=lambda x: -len(x[1])):
        slug = _slugify(cust_name)
        if not slug:
            skipped += len(cust_sites)
            continue

        # Create tenant if it doesn't exist
        if slug not in existing_tenants:
            tenant = Tenant(tenant_id=slug, name=cust_name)
            db.add(tenant)
            existing_tenants.add(slug)
            tenants_created += 1

        # Reassign sites
        site_ids = []
        for site in cust_sites:
            if site.tenant_id != slug:
                site.tenant_id = slug
                sites_reassigned += 1
            site_ids.append(site.site_id)

        # Reassign devices that belong to these sites
        dev_result = await db.execute(
            select(Device).where(Device.site_id.in_(site_ids))
        )
        devs = dev_result.scalars().all()
        dev_count = 0
        for d in devs:
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
