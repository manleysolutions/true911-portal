from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_password_strength,
    verify_password,
)

router = APIRouter()


async def _ensure_tenant(db: AsyncSession, tenant_id: str) -> None:
    """Create the tenant row if it doesn't exist yet (idempotent)."""
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    if not result.scalar_one_or_none():
        db.add(Tenant(tenant_id=tenant_id, name=tenant_id.title()))
        await db.flush()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check password strength
    pwd_err = validate_password_strength(body.password)
    if pwd_err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, pwd_err)

    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    # Ensure the tenant row exists (FK constraint on users.tenant_id)
    await _ensure_tenant(db, body.tenant_id)

    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        tenant_id=body.tenant_id,
        role="User",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access = create_access_token(user.id, user.tenant_id, user.role)
    refresh = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    access = create_access_token(user.id, user.tenant_id, user.role)
    refresh = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    access = create_access_token(user.id, user.tenant_id, user.role)
    new_refresh = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        user=UserOut.model_validate(user),
    )
