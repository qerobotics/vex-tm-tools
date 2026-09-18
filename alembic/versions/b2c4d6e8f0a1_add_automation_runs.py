"""add automation_runs table

Revision ID: b2c4d6e8f0a1
Revises: 1f22770b6d2e
Create Date: 2026-09-11 00:00:00.000000

Wave 3a (Automation Engine) addendum. The plan's §8 schema does not define a
table for the per-automation execution history required by Appendix A.7
("Automation execution history ... Shows: triggered at, trigger event,
success/failure status, which action failed (if any)"). This is a new,
additive table — no existing migration is edited. Chains off
`1f22770b6d2e`, the merge migration that reconciles Wave 2b/2c's divergent
heads (the current `alembic upgrade head`).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2c4d6e8f0a1"
down_revision: Union[str, None] = "1f22770b6d2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automation_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "automation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("trigger_event", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="success"),
        sa.Column("failed_action_index", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_automation_runs_automation_id_triggered_at",
        "automation_runs",
        ["automation_id", "triggered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_automation_runs_automation_id_triggered_at", table_name="automation_runs")
    op.drop_table("automation_runs")
