import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    tenant_id: str = "default"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserOut"
    must_change_password: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    tenant_id: str
    is_active: bool = True
    updated_at: Optional[datetime] = None
    must_change_password: bool = False
    # Computed by the auth router from the user's REAL tenant_id + role.
    # True for SuperAdmin and for any user whose home tenant is listed
    # in settings.INTERNAL_TENANT_IDS.  The frontend gates internal-only
    # surfaces (Registration review queue, conversion workflow) on this
    # flag combined with "not currently impersonating."
    is_platform_user: bool = False

    model_config = {"from_attributes": True}


class InviteInfoResponse(BaseModel):
    email: str
    name: str
    role: str


class InviteAcceptRequest(BaseModel):
    password: str
    name: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AdminResetPasswordRequest(BaseModel):
    new_password: str


TokenResponse.model_rebuild()
