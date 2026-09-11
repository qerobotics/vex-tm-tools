"""seed default role_permissions (plan §13)

Revision ID: b2c3d4e5f6a7
Revises: 1f22770b6d2e
Create Date: 2026-09-11 00:00:00.000000

Seeds the "Suggested Default Group Mappings" table from plan §13 into
`role_permissions`. `qecomp-admin` is seeded with the single sentinel
`"*"` row (meaning "all permissions" — see
`backend.core.dependencies.ALL_PERMISSIONS`) rather than one row per
permission, since the permission list is expected to grow over time and a
sentinel avoids this migration going stale.

These are *editable defaults* (plan §13: "seeded in DB, editable from UI")
— `ON CONFLICT DO NOTHING` so re-running against a DB where an operator has
already customized `qecomp-admin`'s mapping doesn't clobber it.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "1f22770b6d2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_MAPPINGS: dict[str, list[str]] = {
    "qecomp-admin": ["*"],
    "qecomp-operator": [
        "integrations:read",
        "automations:read",
        "automations:trigger",
        "timers:read",
        "teams:read",
        "teams:edit",
        "video:upload",
        "vfx:control",
        "video:control",
        "audio:control",
        "tm:control",
        "overlays:read",
        "prompter:edit",
    ],
    "qecomp-lighting": ["vfx:control", "integrations:read"],
    "qecomp-video": ["video:control", "video:upload", "overlays:read", "overlays:edit"],
    "qecomp-emcee": ["prompter:view", "prompter:control"],
    "qecomp-viewer": ["teams:read", "integrations:read", "automations:read"],
}


def upgrade() -> None:
    role_permissions = sa.table(
        "role_permissions",
        sa.column("authentik_group", sa.String),
        sa.column("permission", sa.String),
    )
    rows = [
        {"authentik_group": group, "permission": permission}
        for group, permissions in _DEFAULT_MAPPINGS.items()
        for permission in permissions
    ]
    if rows:
        stmt = sa.dialects.postgresql.insert(role_permissions).values(rows).on_conflict_do_nothing(
            index_elements=["authentik_group", "permission"]
        )
        op.execute(stmt)


def downgrade() -> None:
    role_permissions = sa.table(
        "role_permissions",
        sa.column("authentik_group", sa.String),
        sa.column("permission", sa.String),
    )
    groups = list(_DEFAULT_MAPPINGS.keys())
    op.execute(role_permissions.delete().where(role_permissions.c.authentik_group.in_(groups)))
