"""seed prompter_index_token system_settings key

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-18 00:00:00.000000

Appendix B.4 (Teleprompter Index Page) gates the bare `GET /prompter` index
page — which lists every active `TimerInstance` with a direct per-instance
teleprompter link — behind a `?token=<value>` query param checked against a
`prompter_index_token` system_settings row. That row was never seeded by any
prior migration (the initial schema migration `8c603463c7a8` only seeded
`s3`, `robot_events_api`, `predictor`, and `chroma_key_defaults`, and
`c3d4e5f6a7b8` added `notifications`), so without this migration the page
would 403 unconditionally until an operator manually PUTs a value via the
generic `PUT /api/v1/settings` endpoint.

Seeds a randomly-generated default token (rather than an empty string) so
the index page is usable out of the box while still requiring the token to
be known — matching Appendix B.4's security model (the index page itself is
gated the same way the per-instance teleprompter links are, by possession of
an unguessable value). An operator can rotate it later via the existing
generic settings endpoint.

Per `c3d4e5f6a7b8`'s own precedent, do not edit an already-applied migration
to add a new seed row — add an additive one instead. Chains off
`c3d4e5f6a7b8`, the current head.
"""
from __future__ import annotations

import json
import secrets
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    default_token = secrets.token_urlsafe(32)
    value_json = json.dumps({"token": default_token})
    op.execute(
        f"""
        INSERT INTO system_settings (key, value) VALUES
          ('prompter_index_token', '{value_json}'::jsonb)
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE key = 'prompter_index_token'")
