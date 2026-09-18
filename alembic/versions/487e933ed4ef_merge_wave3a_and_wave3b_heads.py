"""merge wave3a and wave3b heads

Revision ID: 487e933ed4ef
Revises: b2c4d6e8f0a1, b2c3d4e5f6a7
Create Date: 2026-09-11 20:33:51.837853

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '487e933ed4ef'
down_revision: Union[str, None] = ('b2c4d6e8f0a1', 'b2c3d4e5f6a7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
