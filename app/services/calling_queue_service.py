from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.campaign_lead import CampaignLead
from app.models.lead import Lead
from app.models.enums import CampaignStatus, LeadStatus
from app.schemas.calling_queue import CallingQueueItem

def get_calling_queue(
    db: Session,
    campaign_id: int,
    limit: int = 50,
) -> list[CallingQueueItem]:

    statement = (
        select(Campaign, CampaignLead, Lead)
        .join(
            CampaignLead,
            Campaign.id == CampaignLead.campaign_id,
        )
        .join(
            Lead,
            Lead.id == CampaignLead.lead_id,
        )
        .where(
            Campaign.id == campaign_id,
            Campaign.status == CampaignStatus.ACTIVE,
            Lead.status.in_(
                [
                    LeadStatus.NEW,
                    LeadStatus.QUEUED,
                    LeadStatus.CALLBACK,
                ]
            ),
            CampaignLead.attempt_count < Campaign.max_attempts,
            or_(
                Lead.next_call_at.is_(None),
                Lead.next_call_at <= datetime.utcnow(),
            ),
        )
        .order_by(
            Lead.lead_score.desc(),
            Lead.id.asc(),
        )
        .limit(limit)
    )

    rows = db.execute(statement).all()

    return [
        CallingQueueItem(
            campaign_id=campaign.id,
            campaign_name=campaign.name,
            lead_id=lead.id,
            lead_name=lead.name,
            phone=lead.phone,
            lead_status=lead.status.value,
            lead_score=lead.lead_score,
            attempt_count=campaign_lead.attempt_count,
            max_attempts=campaign.max_attempts,
            next_call_at=lead.next_call_at,
        )
        for campaign, campaign_lead, lead in rows
    ]