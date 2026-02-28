from typing import Optional

from pydantic import BaseModel


class WebhookAck(BaseModel):
    payload_id: str
    job_id: Optional[int] = None
    message: str = "accepted"
