"""seed notifications (ntfy) system_settings key

Revision ID: c3d4e5f6a7b8
Revises: 487e933ed4ef
Create Date: 2026-09-18 00:00:00.000000

Appendix A.8 (ntfy notifications) requires a `notifications` system_settings
row holding `server_url`/`topic`/`enabled` — never seeded by the initial
schema migration (`8c603463c7a8`), which only seeded `s3`,
`robot_events_api`, `predictor`, and `chroma_key_defaults`. Per that
migration's own comment ("Seed required settings keys (plan §8)"), do not
edit an already-applied migration to add a new seed row — add an additive
one instead. Chains off `487e933ed4ef`, the current merge head (Wave 3a/3b).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "487e933ed4ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (key, value) VALUES
          ('notifications', '{"server_url": "", "topic": "", "enabled": false}')
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE key = 'notifications'")
