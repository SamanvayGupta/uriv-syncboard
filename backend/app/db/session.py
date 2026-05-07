"""
uriv-syncboard / backend / app / db / session.py
──────────────────────────────────────────────────
Async SQLAlchemy engine and session factory.

Usage in route handlers
───────────────────────
    async def my_route(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Board))
        ...
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo        = False,        # set True to log SQL statements
    pool_size   = 10,
    max_overflow= 20,
    pool_pre_ping=True,
)

# ── Session factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind       = engine,
    class_     = AsyncSession,
    expire_on_commit = False,
    autocommit = False,
    autoflush  = False,
)


# ── Dependency ────────────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
