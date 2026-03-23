import uuid
from typing import AsyncGenerator

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.device import Device
from app.models.tenant import Tenant
from app.models.user import User
from app.services.auth import decode_token
from app.services.rbac import can as rbac_can, normalize_role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    x_act_as_tenant: str | None = Header(None),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    # Normalize role to canonical PascalCase (handles "superadmin" -> "SuperAdmin" etc.)
    user.role = normalize_role(user.role)

    # Always store the original tenant_id for audit purposes
    user._original_tenant_id = user.tenant_id

    if x_act_as_tenant:
        if user.role != "SuperAdmin":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Only SuperAdmin can act as another tenant",
            )
        # Validate the target tenant exists
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.tenant_id == x_act_as_tenant)
        )
        if not tenant_result.scalar_one_or_none():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Tenant '{x_act_as_tenant}' does not exist",
            )
        # Detach user from session so tenant_id override never flushes to DB
        db.expunge(user)
        user.tenant_id = x_act_as_tenant

    return user


_GENERIC_DEVICE_AUTH_ERROR = "Invalid device credentials"


async def authenticate_device(
    device_id: str,
    raw_key: str,
    db: AsyncSession,
) -> Device:
    """Lookup device by device_id and verify raw_key against stored hash.

    Returns the Device ORM object on success.
    Raises 403 with a generic message on any failure — intentionally does
    not distinguish between "device not found" and "wrong key" to prevent
    enumeration.
    """
    result = await db.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device or not device.api_key_hash:
        raise HTTPException(status.HTTP_403_FORBIDDEN, _GENERIC_DEVICE_AUTH_ERROR)

    if not bcrypt.checkpw(raw_key.encode("utf-8")[:72], device.api_key_hash.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, _GENERIC_DEVICE_AUTH_ERROR)

    return device


def require_permission(action: str):
    """Returns a FastAPI dependency that enforces an RBAC permission."""

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if not rbac_can(current_user.role, action):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Permission '{action}' denied for role '{current_user.role}'",
            )
        return current_user

    return _check
