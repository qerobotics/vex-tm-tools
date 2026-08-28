"""Async Redis client.

Per Appendix A.9, the app treats Redis as a single endpoint (`REDIS_URL`).
HAProxy/infra is responsible for Sentinel-aware failover; no Sentinel client
is implemented here.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as redis

from backend.core.settings import settings

redis_client: redis.Redis = redis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """FastAPI dependency yielding the shared Redis client."""
    yield redis_client


async def check_redis_connection() -> bool:
    """Best-effort connectivity check used by /readyz. Never raises.

    Per Appendix A.10, Redis being unavailable must never crash the app —
    callers should treat a False return as "degraded", not fatal.
    """
    try:
        return bool(await redis_client.ping())
    except Exception:
        return False
