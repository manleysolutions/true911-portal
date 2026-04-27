import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.audit_log_entry import AuditLogEntry
from app.models.customer import Customer
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate

router = APIRouter()

# Customer fields DataEntry / Import Operator may correct after import.
# All other fields (status, customer_number, account_number, zoho_*, etc.)
# remain Admin-only.
_DATAENTRY_ALLOWED_FIELDS = frozenset({
    "name",
    "billing_email",
    "billing_phone",
    "billing_address",
})


@router.get(
    "",
    response_model=list[CustomerOut],
    dependencies=[Depends(require_permission("VIEW_CUSTOMERS"))],
)
async def list_customers(
    sort: str | None = Query("-created_at"),
    limit: int = Query(100, le=500),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Customer).where(Customer.tenant_id == current_user.tenant_id)
    if status_filter:
        q = q.where(Customer.status == status_filter)
    if search:
        q = q.where(Customer.name.ilike(f"%{search}%"))
    q = apply_sort(q, Customer, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [CustomerOut.model_validate(c) for c in result.scalars().all()]


@router.get(
    "/{pk}",
    response_model=CustomerOut,
    dependencies=[Depends(require_permission("VIEW_CUSTOMERS"))],
)
async def get_customer(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Customer).where(
            Customer.id == pk, Customer.tenant_id == current_user.tenant_id
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return CustomerOut.model_validate(customer)


@router.post(
    "",
    response_model=CustomerOut,
    status_code=201,
    dependencies=[Depends(require_permission("CREATE_CUSTOMERS"))],
)
async def create_customer(
    body: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = Customer(**body.model_dump(), tenant_id=current_user.tenant_id)
    db.add(customer)
    await db.flush()
    await db.commit()
    await db.refresh(customer)
    return CustomerOut.model_validate(customer)


@router.patch(
    "/{pk}",
    response_model=CustomerOut,
    dependencies=[Depends(require_permission("EDIT_CUSTOMERS"))],
)
async def update_customer(
    pk: int,
    body: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Customer).where(
            Customer.id == pk, Customer.tenant_id == current_user.tenant_id
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")

    updates = body.model_dump(exclude_unset=True)

    if (current_user.role or "").lower() == "dataentry":
        restricted = {k for k in updates if k not in _DATAENTRY_ALLOWED_FIELDS}
        if restricted:
            db.add(AuditLogEntry(
                entry_id=f"field-block-{uuid.uuid4().hex[:12]}",
                tenant_id=current_user.tenant_id,
                category="security",
                action="restricted_field_edit_blocked",
                actor=current_user.email,
                target_type="customer",
                target_id=str(customer.id),
                summary=(
                    f"DataEntry {current_user.email} attempted to edit "
                    f"restricted customer fields: {', '.join(sorted(restricted))}"
                ),
                detail_json=json.dumps({
                    "customer_id": customer.id,
                    "restricted_fields": sorted(restricted),
                    "allowed_fields": sorted(
                        k for k in updates if k in _DATAENTRY_ALLOWED_FIELDS
                    ),
                }),
            ))
            updates = {k: v for k, v in updates.items() if k in _DATAENTRY_ALLOWED_FIELDS}
        if not updates:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Your role does not allow editing the requested fields.",
            )

    for field, value in updates.items():
        setattr(customer, field, value)
    await db.commit()
    await db.refresh(customer)
    return CustomerOut.model_validate(customer)


@router.delete(
    "/{pk}",
    response_model=CustomerOut,
    dependencies=[Depends(require_permission("DELETE_CUSTOMERS"))],
)
async def delete_customer(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: sets status to 'inactive'."""
    result = await db.execute(
        select(Customer).where(
            Customer.id == pk, Customer.tenant_id == current_user.tenant_id
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    customer.status = "inactive"
    await db.commit()
    await db.refresh(customer)
    return CustomerOut.model_validate(customer)
