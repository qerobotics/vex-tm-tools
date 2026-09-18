"""Integration clients live in per-domain subfolders of this package
(`backend/modules/integrations/<domain>/`), built starting in Wave 2.

The `Integration` ABC is defined in `backend.modules.integrations.base` and
re-exported here for convenience.
"""
from backend.modules.integrations.base import Integration

__all__ = ["Integration"]
