"""merge wave2b and wave2c heads

Revision ID: 1f22770b6d2e
Revises: a1b2c3d4e5f6, e015040b23ac
Create Date: 2026-09-09 19:28:43.914236

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f22770b6d2e'
down_revision: Union[str, None] = ('a1b2c3d4e5f6', 'e015040b23ac')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
