"""add free trial call lifecycle data

Revision ID: d3ef7b28a910
Revises: c865ae81ed68
Create Date: 2026-08-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3ef7b28a910"
down_revision: Union[str, Sequence[str], None] = "c865ae81ed68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE callstatus ADD VALUE IF NOT EXISTS 'IN_PROGRESS'")

    op.add_column("calls", sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("calls", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("calls", sa.Column("next_retry_at", sa.DateTime(), nullable=True))
    op.add_column("calls", sa.Column("retry_reason", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_calls_next_retry_at"), "calls", ["next_retry_at"], unique=False)
    if bind.dialect.name != "sqlite":
        op.create_unique_constraint(
            "uq_campaign_lead_assignment",
            "campaign_leads",
            ["campaign_id", "lead_id"],
        )

    op.create_table(
        "call_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("previous_status", sa.String(length=50), nullable=True),
        sa.Column("new_status", sa.String(length=50), nullable=True),
        sa.Column("provider_event_id", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_event_id"),
    )
    op.create_index(op.f("ix_call_events_call_id"), "call_events", ["call_id"], unique=False)
    op.create_index(op.f("ix_call_events_event_type"), "call_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_call_events_created_at"), "call_events", ["created_at"], unique=False)

    op.create_table(
        "call_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_id", "sequence", name="uq_call_message_sequence"),
    )
    op.create_index(op.f("ix_call_messages_call_id"), "call_messages", ["call_id"], unique=False)

    op.create_table(
        "call_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("customer_intent", sa.String(length=100), nullable=True),
        sa.Column("interest_level", sa.String(length=30), nullable=True),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("objections", sa.Text(), nullable=True),
        sa.Column("next_action", sa.String(length=255), nullable=True),
        sa.Column("qualification_status", sa.String(length=30), nullable=False),
        sa.Column("qualification", sa.JSON(), nullable=False),
        sa.Column("followup_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_id"),
    )


def downgrade() -> None:
    op.drop_table("call_summaries")
    op.drop_index(op.f("ix_call_messages_call_id"), table_name="call_messages")
    op.drop_table("call_messages")
    op.drop_index(op.f("ix_call_events_created_at"), table_name="call_events")
    op.drop_index(op.f("ix_call_events_event_type"), table_name="call_events")
    op.drop_index(op.f("ix_call_events_call_id"), table_name="call_events")
    op.drop_table("call_events")
    op.drop_index(op.f("ix_calls_next_retry_at"), table_name="calls")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("uq_campaign_lead_assignment", "campaign_leads", type_="unique")
    op.drop_column("calls", "retry_reason")
    op.drop_column("calls", "next_retry_at")
    op.drop_column("calls", "max_attempts")
    op.drop_column("calls", "attempt_number")
