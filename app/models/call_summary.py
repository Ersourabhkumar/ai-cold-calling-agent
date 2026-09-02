from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class CallSummary(Base):
    __tablename__ = "call_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    customer_intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    interest_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    objections: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qualification_status: Mapped[str] = mapped_column(
        String(30), default="UNKNOWN", nullable=False
    )
    qualification: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    followup_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    call = relationship("Call", back_populates="summary")
