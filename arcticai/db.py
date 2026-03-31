from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def database_url() -> str:
    # Prefer Postgres in production; fall back to local SQLite for quick dev.
    return os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./arcticai.db")


engine: AsyncEngine = create_async_engine(database_url(), future=True, echo=False)
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session

