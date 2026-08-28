"""add raw_video_s3_key to team_profiles

Revision ID: e015040b23ac
Revises: 8c603463c7a8
Create Date: 2026-08-28 17:18:06.455173

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e015040b23ac'
down_revision: Union[str, None] = '8c603463c7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "team_profiles",
        sa.Column("raw_video_s3_key", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("team_profiles", "raw_video_s3_key")
