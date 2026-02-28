from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class JobOut(BaseModel):
    id: int
    job_type: str
    queue: str
    status: str
    tenant_id: Optional[str] = None
    attempt: int
    max_attempts: int
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class JobDetailOut(JobOut):
    payload: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    idempotency_key: Optional[str] = None
