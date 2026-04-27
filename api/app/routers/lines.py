import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.audit_log_entry import AuditLogEntry
from app.models.line import Line
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.line import LineCreate, LineOut, LineUpdate

router = APIRouter()

_LINE_CONFLICT_MSG = "A line with this DID already exists in your tenant"

# Fields DataEntry / Import Operator may set on a voice line.  status,
# e911_status (validation engine output), reconciliation, import-batch
# bookkeeping, and the FK fields stay Admin-only.
_DATAENTRY_ALLOWED_FIELDS = frozenset({
    "provider",
    "did",
    "sip_uri",
    "protocol",
    "site_id",
    "device_id",
    "e911_street",
    "e911_city",
    "e911_state",
    "e911_zip",
    "sim_iccid",
    "carrier",
    "line_type",
    "notes",
})

# line_id is required at create time and therefore allowed for DataEntry on POST.
_DATAENTRY_ALLOWED_CREATE_FIELDS = _DATAENTRY_ALLOWED_FIELDS | {"line_id"}


def _parse_line_conflict(e: IntegrityError) -> str:
    msg = str(e.orig) if e.orig else str(e)
    if "uq_lines_did_tenant" in msg:
        return _LINE_CONFLICT_MSG
    return "Duplicate value: a line with one of these identifiers already exists"


async def _assert_no_did_conflict(
    db: AsyncSession,
    tenant_id: str,
    updates: dict,
    current_line: Line | None,
) -> None:
    """Raise 409 if the incoming DID is already in use by another line in the
    same tenant.  Pre-flight check that complements the DB unique constraint
    (uq_lines_did_tenant) by naming the conflicting line.
    """
    new_did = updates.get("did")
    if not new_did:
        return
    if current_line is not None and current_line.did == new_did:
        return
    q = select(Line).where(Line.did == new_did, Line.tenant_id == tenant_id)
    if current_line is not None:
        q = q.where(Line.id != current_line.id)
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "field": "did",
                "value": new_did,
                "conflicting_line_id": existing.line_id,
                "message": (
                    f"DID {new_did} is already assigned to line {existing.line_id}."
                ),
            },
        )


@router.get("", response_model=list[LineOut])
async def list_lines(
    sort: str | None = Query("-created_at"),
    limit: int = Query(100, le=500),
    site_id: str | None = None,
    device_id: str | None = None,
    provider: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    e911_status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Line).where(Line.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(Line.site_id == site_id)
    if device_id:
        q = q.where(Line.device_id == device_id)
    if provider:
        q = q.where(Line.provider == provider)
    if status_filter:
        q = q.where(Line.status == status_filter)
    if e911_status:
        q = q.where(Line.e911_status == e911_status)
    q = apply_sort(q, Line, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [LineOut.model_validate(r) for r in result.scalars().all()]


@router.get("/{line_pk}", response_model=LineOut)
async def get_line(
    line_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Line).where(Line.id == line_pk, Line.tenant_id == current_user.tenant_id)
    )
    line = result.scalar_one_or_none()
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")
    return LineOut.model_validate(line)


@router.post(
    "",
    response_model=LineOut,
    status_code=201,
    dependencies=[Depends(require_permission("CREATE_LINES"))],
)
async def create_line(
    body: LineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fields = body.model_dump()

    if (current_user.role or "").lower() == "dataentry":
        restricted = {k for k, v in body.model_dump(exclude_unset=True).items()
                      if k not in _DATAENTRY_ALLOWED_CREATE_FIELDS}
        if restricted:
            db.add(AuditLogEntry(
                entry_id=f"field-block-{uuid.uuid4().hex[:12]}",
                tenant_id=current_user.tenant_id,
                category="security",
                action="restricted_field_create_blocked",
                actor=current_user.email,
                target_type="line",
                site_id=fields.get("site_id"),
                summary=(
                    f"DataEntry {current_user.email} attempted to set "
                    f"restricted line fields on create: {', '.join(sorted(restricted))}"
                ),
                detail_json=json.dumps({
                    "line_id": fields.get("line_id"),
                    "restricted_fields": sorted(restricted),
                }),
            ))
            fields = {k: v for k, v in fields.items() if k in _DATAENTRY_ALLOWED_CREATE_FIELDS}

    await _assert_no_did_conflict(db, current_user.tenant_id, fields, current_line=None)

    line = Line(**fields, tenant_id=current_user.tenant_id)
    db.add(line)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_parse_line_conflict(e))
    await db.commit()
    await db.refresh(line)
    return LineOut.model_validate(line)


@router.patch(
    "/{line_pk}",
    response_model=LineOut,
    dependencies=[Depends(require_permission("EDIT_LINES"))],
)
async def update_line(
    line_pk: int,
    body: LineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Line).where(Line.id == line_pk, Line.tenant_id == current_user.tenant_id)
    )
    line = result.scalar_one_or_none()
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")

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
                target_type="line",
                target_id=str(line.id),
                site_id=line.site_id,
                summary=(
                    f"DataEntry {current_user.email} attempted to edit "
                    f"restricted line fields: {', '.join(sorted(restricted))}"
                ),
                detail_json=json.dumps({
                    "line_id": line.line_id,
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

    await _assert_no_did_conflict(db, current_user.tenant_id, updates, current_line=line)

    for field, value in updates.items():
        setattr(line, field, value)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_parse_line_conflict(e))
    await db.commit()
    await db.refresh(line)
    return LineOut.model_validate(line)


@router.delete(
    "/{line_pk}",
    status_code=204,
    dependencies=[Depends(require_permission("DELETE_LINES"))],
)
async def delete_line(
    line_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Line).where(Line.id == line_pk, Line.tenant_id == current_user.tenant_id)
    )
    line = result.scalar_one_or_none()
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")

    audit = AuditLogEntry(
        entry_id=f"delete-line-{uuid.uuid4().hex[:12]}",
        tenant_id=current_user.tenant_id,
        category="destructive",
        action="delete_line",
        actor=current_user.email,
        target_type="line",
        target_id=str(line.id),
        summary=f"Line {line.line_id} (DID: {line.did or 'none'}) deleted by {current_user.email}",
        detail_json=json.dumps({
            "line_id": line.line_id,
            "did": line.did,
            "site_id": line.site_id,
            "device_id": line.device_id,
        }),
    )
    db.add(audit)
    await db.delete(line)
    await db.commit()
