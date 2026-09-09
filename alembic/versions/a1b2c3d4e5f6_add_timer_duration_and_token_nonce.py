"""add timer_instances.duration_s and token_nonce

Revision ID: a1b2c3d4e5f6
Revises: 8c603463c7a8
Create Date: 2026-08-28 17:30:00.000000

Wave 2b (Timer & Prompter) addendum — see docstring in
`backend/models/timer.py`. The plan's §8 schema for `timer_instances` omits a
countdown-duration column despite Appendix A.3 requiring a per-instance,
UI-configurable duration in seconds, and Appendix B.8 requires a per-instance
nonce so the teleprompter HMAC token can be regenerated (invalidating old
links). Both are additive, backward-compatible columns on the existing
table — Wave 1's initial migration is left untouched.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "8c603463c7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "timer_instances",
        sa.Column(
            "duration_s",
            sa.Integer(),
            nullable=False,
            server_default="120",
        ),
    )
    op.add_column(
        "timer_instances",
        sa.Column(
            "token_nonce",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("encode(gen_random_bytes(16), 'hex')"),
        ),
    )


def downgrade() -> None:
    op.drop_column("timer_instances", "token_nonce")
    op.drop_column("timer_instances", "duration_s")
