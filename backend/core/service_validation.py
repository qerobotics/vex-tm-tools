"""Validates a service-call payload against its domain's `services.yaml`
schema (plan §9/§11) before it reaches `Integration.call_service()`.

Each `backend/modules/integrations/<domain>/services.yaml` declares, per
service, a `fields` map of `{field_name: {type, required, secret?}}`.
Nothing previously checked an incoming `POST
/api/v1/integrations/{entity_id}/service/{service}` body against that
schema, so a missing required field surfaced as an unhandled `KeyError`
deep inside the integration (a 500) instead of a clean 400 at the API
boundary. `validate_service_data()` closes that gap.

Uses the same `yaml.safe_load` pattern already used for `manifest.yaml` /
`services.yaml` elsewhere (see `backend/loader.py`'s `_discover()` and
`backend/routers/integrations.py`'s `_load_manifests()`) rather than
introducing a new parsing convention.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.loader import INTEGRATIONS_DIR

logger = logging.getLogger(__name__)


class ServiceValidationError(ValueError):
    """Raised by `validate_service_data()` when a service-call payload is
    missing required fields (or the service/domain itself is unknown).
    Subclasses `ValueError` so existing `except ValueError` handlers around
    integration calls (e.g. `routers/integrations.py`'s
    `call_integration_service`) keep working unchanged."""


@lru_cache(maxsize=None)
def _load_services_yaml(domain: str) -> dict[str, Any]:
    """Loads and caches `modules/integrations/<domain>/services.yaml`.
    Returns `{}` if the domain or file doesn't exist / fails to parse —
    callers treat "no schema" as "nothing to validate" rather than an error,
    since not every domain necessarily ships one."""
    path: Path = INTEGRATIONS_DIR / domain / "services.yaml"
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        logger.exception("Failed to parse services.yaml for domain %r", domain)
        return {}


def get_service_schema(domain: str, service: str) -> dict[str, Any] | None:
    """Returns the `fields` schema dict for one `domain`/`service` pair, or
    `None` if the domain has no `services.yaml` or no such service is
    declared in it."""
    services = _load_services_yaml(domain).get("services") or {}
    spec = services.get(service)
    if not spec:
        return None
    return spec.get("fields") or {}


def validate_service_data(domain: str, service: str, data: dict[str, Any]) -> None:
    """Validates `data` (the incoming service-call body) against
    `domain`'s `services.yaml` schema for `service`.

    Raises `ServiceValidationError` (a `ValueError` subclass) listing any
    missing required fields. Does nothing if the domain/service isn't
    declared in a `services.yaml` at all — schema coverage is opt-in per
    domain, so an undeclared service isn't itself a validation failure
    (the integration's own `call_service` is still responsible for
    rejecting genuinely unknown service names with its own `ValueError`).
    """
    fields = get_service_schema(domain, service)
    if not fields:
        return

    data = data or {}
    missing = [
        name
        for name, spec in fields.items()
        if (spec or {}).get("required") and name not in data
    ]
    if missing:
        raise ServiceValidationError(
            f"Missing required field(s) for {domain}.{service}: {', '.join(sorted(missing))}"
        )


def redact_service_data(domain: str, service: str, data: dict[str, Any]) -> dict[str, Any]:
    """Returns a copy of `data` with any field marked `secret: true` in
    `services.yaml` masked out — for safe inclusion in audit-log `changes`
    payloads (plan §8), mirroring `routers/integrations.py`'s
    `_redact_secrets()` for `config_schema` fields."""
    fields = get_service_schema(domain, service) or {}
    out = dict(data or {})
    for name, spec in fields.items():
        if (spec or {}).get("secret") and name in out:
            out[name] = "••••••••"
    return out
