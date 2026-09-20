"""add video_processing_error to team_profiles

Revision ID: f7a8b9c0d1e2
Revises: d4e5f6a7b8c9
Create Date: 2026-09-20 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "team_profiles",
        sa.Column("video_processing_error", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("team_profiles", "video_processing_error")
