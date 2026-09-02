from datetime import datetime

from pydantic import BaseModel


class CallingQueueItem(BaseModel):
    campaign_id: int
    campaign_name: str

    lead_id: int
    lead_name: str
    phone: str

    lead_status: str
    lead_score: int

    attempt_count: int
    max_attempts: int

    next_call_at: datetime | None