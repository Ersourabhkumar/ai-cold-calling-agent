from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import LeadStatus


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    phone: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    requirement: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    budget: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    timeline: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus),
        default=LeadStatus.NEW,
        nullable=False,
        index=True,
    )

    lead_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    last_called_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    next_call_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    campaign_links = relationship(
        "CampaignLead",
        back_populates="lead",
        cascade="all, delete-orphan",
    )

    followups = relationship(
        "Followup",
        back_populates="lead",
        cascade="all, delete-orphan",
    )
    calls = relationship(
    "Call",
    back_populates="lead",
    cascade="all, delete-orphan",
    )