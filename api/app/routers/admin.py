from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission, get_current_user
from app.models.user import User

router = APIRouter()

ALLOWED_ROLES = {"Admin", "Manager", "User"}


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    tenant_id: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RoleUpdate(BaseModel):
    role: str


@router.get(
    "/users",
    response_model=list[UserOut],
    dependencies=[Depends(require_permission("VIEW_ADMIN"))],
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
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@router.put(
    "/users/{user_id}/role",
    response_model=UserOut,
    dependencies=[Depends(require_permission("VIEW_ADMIN"))],
)
async def update_user_role(
    user_id: int,
    body: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote/demote a user's role. Admin only."""
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
    return UserOut.model_validate(user)
