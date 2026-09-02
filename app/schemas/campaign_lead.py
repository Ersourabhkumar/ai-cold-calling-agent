from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CampaignLeadCreate(BaseModel):
    campaign_id: int
    lead_id: int


class CampaignLeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    lead_id: int
    attempt_count: int
    created_at: datetime