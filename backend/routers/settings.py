"""Settings, API keys, roles, and ZerOS presets API (plan §11 "Settings &
Users").

Thin CRUD router over `system_settings`, `api_keys`, `role_permissions`, and
`zeros_presets`. Per §C.2, no business logic lives here.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_db, require_permission
from backend.core.security import generate_api_key, hash_api_key
from backend.models.integration import ZerosPreset
from backend.models.settings import ApiKey, RolePermission, SystemSetting
from backend.schemas.integration import ZerosPresetCreate, ZerosPresetRead
from backend.schemas.settings import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyRead,
    RolePermissionRead,
    SystemSettingRead,
    SystemSettingUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["settings"])


# ── system_settings (plan §11 / Appendix A.8 / §3.8) ─────────────────────


@router.get(
    "/settings",
    response_model=list[SystemSettingRead],
    dependencies=[Depends(require_permission("settings:read"))],
)
async def list_settings(db: Annotated[AsyncSession, Depends(get_db)]) -> list[SystemSetting]:
    result = await db.execute(select(SystemSetting).order_by(SystemSetting.key))
    return list(result.scalars().all())


@router.put(
    "/settings",
    response_model=list[SystemSettingRead],
    dependencies=[Depends(require_permission("settings:edit"))],
)
async def update_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    body: dict[str, SystemSettingUpdate] = Body(...),
) -> list[SystemSetting]:
    """Upserts one or more `system_settings` rows in a single call, e.g.
    `{"s3": {"value": {...}}, "predictor": {"value": {...}}}` (plan §11's
    S3/Robot Events/predictor/chroma-key/ntfy settings groups, Appendix
    A.8/§3.8)."""
    rows: list[SystemSetting] = []
    for key, update in body.items():
        row = await db.get(SystemSetting, key)
        if row is None:
            row = SystemSetting(key=key, value=update.value)
            db.add(row)
        else:
            row.value = update.value
        rows.append(row)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


# ── api_keys (plan §11 / Appendix B.7) ────────────────────────────────────


@router.get(
    "/api-keys",
    response_model=list[ApiKeyRead],
    dependencies=[Depends(require_permission("settings:edit"))],
)
async def list_api_keys(db: Annotated[AsyncSession, Depends(get_db)]) -> list[ApiKey]:
    result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return list(result.scalars().all())


@router.post(
    "/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=201,
    dependencies=[Depends(require_permission("settings:edit"))],
)
async def create_api_key(
    body: ApiKeyCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> ApiKeyCreateResponse:
    raw_key = generate_api_key()
    row = ApiKey(
        name=body.name,
        key_hash=hash_api_key(raw_key),
        permissions=body.permissions,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    # The raw key is shown exactly once (plan Appendix B.7) — never
    # retrievable again after this response.
    return ApiKeyCreateResponse(**ApiKeyRead.model_validate(row).model_dump(), raw_key=raw_key)


@router.delete(
    "/api-keys/{key_id}",
    status_code=204,
    response_model=None,
    dependencies=[Depends(require_permission("settings:edit"))],
)
async def revoke_api_key(key_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    row = await db.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="API key not found")
    row.revoked = True
    await db.commit()


# ── role_permissions (plan §11 / §13) ────────────────────────────────────


@router.get(
    "/users/roles",
    response_model=list[RolePermissionRead],
    dependencies=[Depends(require_permission("settings:edit"))],
)
async def list_role_permissions(db: Annotated[AsyncSession, Depends(get_db)]) -> list[RolePermission]:
    result = await db.execute(
        select(RolePermission).order_by(RolePermission.authentik_group, RolePermission.permission)
    )
    return list(result.scalars().all())


@router.put(
    "/users/roles",
    response_model=list[RolePermissionRead],
    dependencies=[Depends(require_permission("settings:edit"))],
)
async def replace_role_permissions(
    db: Annotated[AsyncSession, Depends(get_db)],
    body: list[RolePermissionRead] = Body(...),
) -> list[RolePermission]:
    """Replaces the entire `role_permissions` table with `body` (plan §13's
    Users & Roles page: "Add/remove permission for a group" — the frontend
    sends the full desired mapping table on each save)."""
    await db.execute(delete(RolePermission))
    rows = [
        RolePermission(authentik_group=item.authentik_group, permission=item.permission)
        for item in body
    ]
    db.add_all(rows)
    await db.commit()
    result = await db.execute(
        select(RolePermission).order_by(RolePermission.authentik_group, RolePermission.permission)
    )
    return list(result.scalars().all())


# ── zeros_presets (plan §11) ──────────────────────────────────────────────


@router.get(
    "/zeros/presets",
    response_model=list[ZerosPresetRead],
    dependencies=[Depends(require_permission("integrations:read"))],
)
async def list_zeros_presets(db: Annotated[AsyncSession, Depends(get_db)]) -> list[ZerosPreset]:
    result = await db.execute(select(ZerosPreset).order_by(ZerosPreset.preset_number))
    return list(result.scalars().all())


@router.post(
    "/zeros/presets",
    response_model=ZerosPresetRead,
    status_code=201,
    dependencies=[Depends(require_permission("integrations:edit"))],
)
async def create_zeros_preset(
    body: ZerosPresetCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> ZerosPreset:
    row = ZerosPreset(**body.model_dump())
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A ZerOS preset with that number or name already exists"
        ) from None
    await db.refresh(row)
    return row


@router.put(
    "/zeros/presets/{preset_id}",
    response_model=ZerosPresetRead,
    dependencies=[Depends(require_permission("integrations:edit"))],
)
async def update_zeros_preset(
    preset_id: UUID, body: ZerosPresetCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> ZerosPreset:
    row = await db.get(ZerosPreset, preset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="ZerOS preset not found")
    for field_name, value in body.model_dump().items():
        setattr(row, field_name, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A ZerOS preset with that number or name already exists"
        ) from None
    await db.refresh(row)
    return row


@router.delete(
    "/zeros/presets/{preset_id}",
    status_code=204,
    response_model=None,
    dependencies=[Depends(require_permission("integrations:edit"))],
)
async def delete_zeros_preset(preset_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    row = await db.get(ZerosPreset, preset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="ZerOS preset not found")
    await db.delete(row)
    await db.commit()
