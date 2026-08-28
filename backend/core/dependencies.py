"""Shared FastAPI `Depends()` utilities used across routers.

Per Appendix C.2, inter-router dependencies (auth/permission checks, common
query params, etc.) live here rather than being imported router-to-router.

Wave 1 only stubs the extension points needed for health/ready endpoints and
future auth wiring. RBAC/session dependencies (current_user, require_permission)
are added by later waves that own `routers/auth.py` and RBAC — this module is
the place they must be added to keep the "no router imports another router"
rule intact.
"""
from __future__ import annotations

from backend.core.db import check_db_connection, get_db  # noqa: F401
from backend.core.redis import check_redis_connection, get_redis  # noqa: F401

# Extension point: later waves add things like
#
#   async def get_current_user(session: AsyncSession = Depends(get_db), ...) -> User: ...
#   def require_permission(permission: str): ...
#
# here, so every router can `from backend.core.dependencies import require_permission`
# without importing another router module directly.
