"""ASGI middleware that records each request's client IP for `log_action()`
(see `backend.core.audit.current_request_ip`) without threading `Request`
through every router handler that writes an audit row.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from backend.core.audit import current_request_ip


def _client_ip(scope: Scope) -> str | None:
    """Prefers the leftmost `X-Forwarded-For` entry (this stack sits behind
    Traefik, per `local-testing/docker-compose.proxy.yml` / prod's ingress)
    and falls back to the raw ASGI client address."""
    for name, value in scope.get("headers") or []:
        if name == b"x-forwarded-for":
            first = value.decode("latin-1").split(",")[0].strip()
            if first:
                return first
    client = scope.get("client")
    return client[0] if client else None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = current_request_ip.set(_client_ip(scope))
        try:
            await self.app(scope, receive, send)
        finally:
            current_request_ip.reset(token)
