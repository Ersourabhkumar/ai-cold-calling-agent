from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import CallStatus, CallOutcome


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    phone_number: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus),
        default=CallStatus.QUEUED,
        nullable=False,
        index=True,
    )

    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    provider_call_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    duration_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    outcome: Mapped[CallOutcome | None] = mapped_column(
        Enum(CallOutcome),
        nullable=True,
        index=True,
    )

    recording_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    transcript: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )

    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    retry_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
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

    lead = relationship(
        "Lead",
        back_populates="calls",
    )

    campaign = relationship(
        "Campaign",
        back_populates="calls",
    )

    events = relationship(
        "CallEvent",
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="CallEvent.created_at",
    )

    messages = relationship(
        "CallMessage",
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="CallMessage.sequence",
    )

    summary = relationship(
        "CallSummary",
        back_populates="call",
        cascade="all, delete-orphan",
        uselist=False,
    )
