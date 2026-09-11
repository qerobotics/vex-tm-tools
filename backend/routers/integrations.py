"""Integrations API (plan §11 "Integrations").

Per §C.2, this router is thin: CRUD on `integration_instances` (encrypting
`secret: true` config fields per the domain's `manifest.yaml`), publishing
`config_change` so `backend.loader.Loader.reconcile()` hot-reloads, and
otherwise delegating to `backend.loader.get_instance(...).call_service(...)`
/`.get_state()`. No integration business logic lives here.
"""
from __future__ import annotations

import logging
import time
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend import loader
from backend.core.dependencies import get_db, require_permission
from backend.core.redis import get_redis
from backend.core.security import decrypt, encrypt
from backend.loader import INTEGRATIONS_DIR
from backend.models.integration import IntegrationInstance
from backend.schemas.events import EventBusMessage
from backend.schemas.integration import (
    IntegrationInstanceCreate,
    IntegrationInstanceRead,
    IntegrationInstanceUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


# ── helpers ───────────────────────────────────────────────────────────────


async def _get_or_404(db: AsyncSession, entity_id: str) -> IntegrationInstance:
    row = await db.execute(
        select(IntegrationInstance).where(IntegrationInstance.entity_id == entity_id)
    )
    instance = row.scalar_one_or_none()
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Integration {entity_id!r} not found")
    return instance


def _load_manifests() -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    if not INTEGRATIONS_DIR.exists():
        return manifests
    for domain_dir in sorted(p for p in INTEGRATIONS_DIR.iterdir() if p.is_dir()):
        manifest_path = domain_dir / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            manifest = yaml.safe_load(manifest_path.read_text()) or {}
            domain = manifest.get("domain") or domain_dir.name
            manifests[domain] = manifest
        except Exception:
            logger.exception("Failed to parse manifest.yaml for %s", domain_dir)
    return manifests


def _encrypt_secrets(domain: str, config: dict[str, Any], manifests: dict[str, Any]) -> dict[str, Any]:
    schema = (manifests.get(domain) or {}).get("config_schema", {}) or {}
    out = dict(config)
    for field, spec in schema.items():
        if spec.get("secret") and out.get(field):
            out[field] = encrypt(str(out[field]))
    return out


def _redact_secrets(domain: str, config: dict[str, Any], manifests: dict[str, Any]) -> dict[str, Any]:
    """Never return a decrypted secret to the client; mask it instead so the
    UI can show "configured" without leaking the value."""
    schema = (manifests.get(domain) or {}).get("config_schema", {}) or {}
    out = dict(config)
    for field, spec in schema.items():
        if spec.get("secret") and out.get(field):
            out[field] = "••••••••"
    return out


async def _publish_config_change(redis_client: Any, entity_id: str, action: str, tags: list[str]) -> None:
    msg = EventBusMessage(
        entity_id=entity_id,
        entity_tags=tags,
        type="config_change",
        timestamp=time.time(),
        payload={"resource_type": "integration_instance", "entity_id": entity_id, "action": action},
    )
    try:
        await redis_client.publish("qecomp:config_change", msg.model_dump_json())
    except Exception:
        logger.exception("Failed to publish config_change for %s", entity_id)


def _to_read(row: IntegrationInstance, manifests: dict[str, Any]) -> IntegrationInstanceRead:
    read = IntegrationInstanceRead.model_validate(row)
    read.config = _redact_secrets(row.domain, dict(row.config or {}), manifests)
    read.status = loader.get_instance_status(row.entity_id)
    return read


# ── schemas endpoint ──────────────────────────────────────────────────────


@router.get("/schemas")
async def list_integration_schemas() -> dict[str, Any]:
    """Lists each domain's `config_schema` from its `manifest.yaml` (plan
    §11) so the frontend's "Add Integration" flow can render a form. No
    permission required (this is static, non-sensitive metadata)."""
    manifests = _load_manifests()
    return {
        domain: {
            "name": manifest.get("name", domain),
            "version": manifest.get("version", ""),
            "description": manifest.get("description", ""),
            "requires_oauth": bool(manifest.get("requires_oauth", False)),
            "config_schema": manifest.get("config_schema", {}),
        }
        for domain, manifest in manifests.items()
    }


# ── CRUD ──────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[IntegrationInstanceRead],
    dependencies=[Depends(require_permission("integrations:read"))],
)
async def list_integrations(db: Annotated[AsyncSession, Depends(get_db)]) -> list[IntegrationInstanceRead]:
    manifests = _load_manifests()
    result = await db.execute(select(IntegrationInstance).order_by(IntegrationInstance.display_name))
    return [_to_read(row, manifests) for row in result.scalars().all()]


@router.post(
    "",
    response_model=IntegrationInstanceRead,
    status_code=201,
    dependencies=[Depends(require_permission("integrations:edit"))],
)
async def create_integration(
    body: IntegrationInstanceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Any = Depends(get_redis),
) -> IntegrationInstanceRead:
    manifests = _load_manifests()
    if body.domain not in manifests:
        raise HTTPException(status_code=400, detail=f"Unknown integration domain {body.domain!r}")

    existing = await db.execute(
        select(IntegrationInstance).where(IntegrationInstance.entity_id == body.entity_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Integration {body.entity_id!r} already exists")

    row = IntegrationInstance(
        entity_id=body.entity_id,
        domain=body.domain,
        display_name=body.display_name,
        config=_encrypt_secrets(body.domain, body.config, manifests),
        enabled=body.enabled,
        tags=body.tags,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Integration {body.entity_id!r} already exists") from None
    await db.refresh(row)

    await _publish_config_change(redis_client, row.entity_id, "created", row.tags)
    return _to_read(row, manifests)


@router.put(
    "/{entity_id}",
    response_model=IntegrationInstanceRead,
    dependencies=[Depends(require_permission("integrations:edit"))],
)
async def update_integration(
    entity_id: str,
    body: IntegrationInstanceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Any = Depends(get_redis),
) -> IntegrationInstanceRead:
    row = await _get_or_404(db, entity_id)
    manifests = _load_manifests()

    if body.display_name is not None:
        row.display_name = body.display_name
    if body.config is not None:
        # Merge rather than replace so a client that doesn't resend a
        # redacted secret field (it never sees the real value, see
        # `_redact_secrets`) doesn't accidentally blank it out.
        merged = dict(row.config or {})
        merged.update(body.config)
        row.config = _encrypt_secrets(row.domain, merged, manifests)
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.tags is not None:
        row.tags = body.tags

    await db.commit()
    await db.refresh(row)

    await _publish_config_change(redis_client, row.entity_id, "updated", row.tags)
    return _to_read(row, manifests)


@router.delete(
    "/{entity_id}",
    status_code=204,
    response_model=None,
    dependencies=[Depends(require_permission("integrations:edit"))],
)
async def delete_integration(
    entity_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Any = Depends(get_redis),
) -> None:
    row = await _get_or_404(db, entity_id)
    tags = list(row.tags or [])
    await db.delete(row)
    await db.commit()
    await _publish_config_change(redis_client, entity_id, "deleted", tags)


# ── service calls / state / oauth (plan §11) ─────────────────────────────


@router.post("/{entity_id}/service/{service}")
async def call_integration_service(
    entity_id: str,
    service: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    data: dict[str, Any] | None = Body(default=None),
    principal=Depends(require_permission("integrations:read")),
) -> dict[str, Any]:
    """Per plan §11, permission for this route "varies by integration"
    (`vfx:control` for zeros.*, `video:control` for atem.*/obs.*,
    `audio:control` for spotify.*, `tm:control` for vex_tm.*). Enforcing a
    single static permission via `Depends()` can't express that
    per-instance-domain branching, so this handler checks the caller's
    resolved permission set directly against the domain -> permission
    mapping below after resolving the instance's domain."""
    row = await _get_or_404(db, entity_id)
    domain_permission = {
        "zeros": "vfx:control",
        "atem": "video:control",
        "obs": "video:control",
        "spotify": "audio:control",
        "vex_tm": "tm:control",
    }.get(row.domain)
    if domain_permission and not principal.has_permission(domain_permission):
        raise HTTPException(status_code=403, detail=f"Missing required permission: {domain_permission!r}")

    instance = loader.get_instance(entity_id)
    if instance is None:
        raise HTTPException(status_code=503, detail=f"Integration {entity_id!r} is not currently running")
    try:
        return await instance.call_service(service, data or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{entity_id}/oauth_token",
    dependencies=[Depends(require_permission("integrations:edit"))],
)
async def set_oauth_token(
    entity_id: str,
    body: dict[str, Any],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Spotify PKCE token-exchange landing point (plan §3.5/§11): the
    frontend performs the browser-side PKCE code exchange with Spotify
    directly (client secret never touches the browser for the user-token
    flow) and POSTs the resulting tokens here for the running integration
    instance to adopt."""
    row = await _get_or_404(db, entity_id)
    if row.domain != "spotify":
        raise HTTPException(status_code=400, detail="oauth_token is only supported for spotify.* instances")

    instance = loader.get_instance(entity_id)
    if instance is None:
        raise HTTPException(status_code=503, detail=f"Integration {entity_id!r} is not currently running")

    access_token = body.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="access_token is required")

    set_tokens = getattr(instance, "set_oauth_tokens", None)
    if set_tokens is None:
        raise HTTPException(status_code=500, detail="Integration instance does not support OAuth tokens")

    await set_tokens(
        access_token=access_token,
        refresh_token=body.get("refresh_token"),
        expires_in=int(body.get("expires_in", 3600)),
    )
    return {"ok": True}


@router.get(
    "/{entity_id}/state",
    dependencies=[Depends(require_permission("integrations:read"))],
)
async def get_integration_state(entity_id: str) -> dict[str, Any]:
    instance = loader.get_instance(entity_id)
    if instance is None:
        return {"entity_id": entity_id, "status": loader.get_instance_status(entity_id), "state": {}}
    state = await instance.get_state()
    return {"entity_id": entity_id, "status": loader.get_instance_status(entity_id), "state": state}


@router.get(
    "/{entity_id}/spotify/library",
    dependencies=[Depends(require_permission("integrations:read"))],
)
async def get_spotify_library(
    entity_id: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict[str, Any]:
    row = await _get_or_404(db, entity_id)
    if row.domain != "spotify":
        raise HTTPException(status_code=400, detail="spotify/library is only supported for spotify.* instances")

    instance = loader.get_instance(entity_id)
    if instance is None:
        raise HTTPException(status_code=503, detail=f"Integration {entity_id!r} is not currently running")
    try:
        return await instance.call_service("browse_library", {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
