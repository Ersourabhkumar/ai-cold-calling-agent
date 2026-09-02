from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.campaign_lead import CampaignLead
from app.models.enums import (
    CampaignStatus,
    FollowupStatus,
    LeadStatus,
)
from app.models.followup import Followup
from app.models.lead import Lead
from app.schemas.call import CallCreate
from app.services.call_service import create_call


def get_active_campaign_for_lead(
    db: Session,
    lead_id: int,
) -> Campaign | None:

    statement = (
        select(Campaign)
        .join(
            CampaignLead,
            CampaignLead.campaign_id
            == Campaign.id,
        )
        .where(
            CampaignLead.lead_id == lead_id,
            Campaign.status
            == CampaignStatus.ACTIVE,
        )
        .order_by(
            Campaign.id.desc()
        )
    )

    return db.scalar(statement)


def process_followup(
    db: Session,
    followup: Followup,
) -> bool:

    if (
        followup.status
        != FollowupStatus.PENDING
    ):
        return False

    lead = db.get(
        Lead,
        followup.lead_id,
    )

    if lead is None:
        followup.status = (
            FollowupStatus.CANCELLED
        )

        db.commit()

        return False

    if lead.status == LeadStatus.DO_NOT_CALL:
        followup.status = (
            FollowupStatus.CANCELLED
        )

        db.commit()

        return False

    campaign = get_active_campaign_for_lead(
        db,
        lead.id,
    )

    if campaign is None:
        return False

    try:

        create_call(
            db,
            CallCreate(
                lead_id=lead.id,
                campaign_id=campaign.id,
            ),
        )

    except ValueError:

        followup.status = (
            FollowupStatus.CANCELLED
        )

        db.commit()

        return False

    followup.status = (
        FollowupStatus.COMPLETED
    )

    db.commit()

    return True