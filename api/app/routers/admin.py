import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission, get_current_user
from app.models.user import User
from app.services.auth import hash_password, validate_password_strength

router = APIRouter()

ALLOWED_ROLES = {"Admin", "Manager", "User"}


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

    model_config = {"from_attributes": True}


class AdminUserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str
    tenant_id: Optional[str] = None  # defaults to current user's tenant


class AdminUserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    name: Optional[str] = None


# Keep backward compat schema for the old PUT endpoint (now subsumed by PATCH)
class RoleUpdate(BaseModel):
    role: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/users",
    response_model=list[AdminUserOut],
    dependencies=[Depends(require_permission("MANAGE_USERS"))],
)
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all users in the current tenant. Admin only."""
    result = await db.execute(
        select(User)
        .where(User.tenant_id == current_user.tenant_id)
        .order_by(User.created_at)
    )
    return [AdminUserOut.model_validate(u) for u in result.scalars().all()]


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
    """Create a new user. Admin only."""
    # Validate role
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Invalid role '{body.role}'. Must be one of: {', '.join(sorted(ALLOWED_ROLES))}",
        )

    # Validate password strength
    pwd_err = validate_password_strength(body.password)
    if pwd_err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, pwd_err)

    # Normalize email to lowercase
    email = body.email.strip().lower()

    # Check duplicate email (case-insensitive)
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
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return AdminUserOut.model_validate(user)


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
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
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

    await db.commit()
    await db.refresh(user)
    return AdminUserOut.model_validate(user)


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

    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
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

    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user.role = body.role
    await db.commit()
    await db.refresh(user)
    return AdminUserOut.model_validate(user)
