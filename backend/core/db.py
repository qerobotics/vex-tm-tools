"""Async SQLAlchemy engine + session factory.

Per Appendix C.2, `backend/core/` may only depend on stdlib + third-party
packages. `backend/models/` imports `Base` from here.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.core.settings import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


engine: AsyncEngine = create_async_engine(
    settings.POSTGRES_DSN,
    pool_pre_ping=True,
    future=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a scoped AsyncSession per request."""
    async with async_session_factory() as session:
        yield session


async def check_db_connection() -> bool:
    """Best-effort connectivity check used by /readyz. Never raises."""
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False
