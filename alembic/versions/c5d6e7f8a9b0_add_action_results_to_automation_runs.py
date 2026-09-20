"""add action_results to automation_runs

Revision ID: c5d6e7f8a9b0
Revises: f7a8b9c0d1e2
Create Date: 2026-09-20 00:00:00.000000

QA HIGH fix (Appendix A.7): `automation_runs.failed_action_index`/`error`
only ever recorded the *first* action failure in a chain, even though a
failed action now correctly retries once and then lets the remaining
actions run (see `AutomationEngine._execute_action_chain`). Multiple
actions in the same chain can each fail independently, so the run history
needs a per-action breakdown, not just a single index. This is purely
additive — the existing `failed_action_index`/`error` columns are left in
place for backwards compatibility.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "automation_runs",
        sa.Column("action_results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("automation_runs", "action_results")
