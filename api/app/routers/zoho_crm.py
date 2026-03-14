"""Zoho CRM integration endpoints — sync accounts, contacts, push status."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.services import zoho_crm

router = APIRouter()


@router.get("/config")
async def zoho_config(current_user: User = Depends(get_current_user)):
    """Return safe Zoho CRM config summary (no secrets)."""
    return zoho_crm.config_summary()


@router.post(
    "/sync/accounts",
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def sync_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pull Zoho CRM Accounts → upsert as True911 Customers."""
    try:
        return await zoho_crm.sync_accounts(db, current_user.tenant_id)
    except zoho_crm.ZohoCRMError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


@router.post(
    "/sync/contacts",
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def sync_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pull Zoho CRM Contacts → update primary contacts on Customers."""
    try:
        return await zoho_crm.sync_contacts(db)
    except zoho_crm.ZohoCRMError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


@router.post(
    "/push/{customer_id}",
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def push_status(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Push True911 operational status to Zoho CRM Account."""
    try:
        return await zoho_crm.push_status_to_zoho(db, customer_id)
    except zoho_crm.ZohoCRMError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


@router.post(
    "/test-connection",
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def test_connection(current_user: User = Depends(get_current_user)):
    """Test Zoho CRM API connectivity."""
    if not zoho_crm.is_configured():
        return {"ok": False, "message": "Zoho CRM not configured. Set ZOHO_CRM_* environment variables."}
    try:
        token = await zoho_crm._get_access_token()
        return {"ok": True, "message": "Successfully authenticated to Zoho CRM", "token_obtained": True}
    except zoho_crm.ZohoCRMError as e:
        return {"ok": False, "message": str(e)}
