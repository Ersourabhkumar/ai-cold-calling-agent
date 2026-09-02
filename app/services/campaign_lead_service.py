from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.campaign_lead import CampaignLead
from app.models.lead import Lead


def assign_lead_to_campaign(
    db: Session,
    campaign_id: int,
    lead_id: int,
) -> CampaignLead:

    campaign = db.get(Campaign, campaign_id)

    if campaign is None:
        raise ValueError("Campaign not found")

    lead = db.get(Lead, lead_id)

    if lead is None:
        raise ValueError("Lead not found")

    existing = db.scalar(
        select(CampaignLead).where(
            CampaignLead.campaign_id == campaign_id,
            CampaignLead.lead_id == lead_id,
        )
    )

    if existing is not None:
        raise ValueError("Lead is already assigned to this campaign")

    campaign_lead = CampaignLead(
        campaign_id=campaign_id,
        lead_id=lead_id,
    )

    db.add(campaign_lead)
    db.commit()
    db.refresh(campaign_lead)

    return campaign_lead


def get_campaign_leads(
    db: Session,
    campaign_id: int,
) -> list[CampaignLead]:

    statement = (
        select(CampaignLead)
        .where(CampaignLead.campaign_id == campaign_id)
        .order_by(CampaignLead.id.desc())
    )

    return list(db.scalars(statement).all())


def remove_lead_from_campaign(
    db: Session,
    campaign_id: int,
    lead_id: int,
) -> bool:

    campaign_lead = db.scalar(
        select(CampaignLead).where(
            CampaignLead.campaign_id == campaign_id,
            CampaignLead.lead_id == lead_id,
        )
    )

    if campaign_lead is None:
        return False

    db.delete(campaign_lead)
    db.commit()

    return True