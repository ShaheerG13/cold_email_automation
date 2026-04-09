"""Shared fixtures for ArcticAI integration tests.

Uses an in-process SQLite database so tests run without Supabase/Postgres.
Mocks the Supabase auth dependency via fake tokens in the Authorization header.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from arcticai.models import Base, User

# ── In-memory SQLite engine for tests ──

TEST_ENGINE = create_async_engine("sqlite+aiosqlite://", echo=False)
TestSession = async_sessionmaker(TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)

# ── Mock users keyed by fake token ──

MOCK_USERS = {
    "token-user1": User(id=1, supabase_uid="uid-1", name="Test", email="test@example.com", is_verified=True, tier="free"),
    "token-user2": User(id=3, supabase_uid="uid-3", name="Other", email="other@example.com", is_verified=True, tier="free"),
    "token-unverified": User(id=2, supabase_uid="uid-2", name="Unverified", email="unverified@example.com", is_verified=False, tier="free"),
}


async def _mock_get_current_user(authorization: str = Header(..., alias="Authorization")) -> User:
    """Look up mock user by token. Raises 401 if not found."""
    from fastapi import HTTPException

    token = authorization.replace("Bearer ", "", 1).strip()
    user = MOCK_USERS.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """Wipe all data between tests for isolation."""
    yield
    async with TestSession() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


def _override_get_db():
    async def _get_test_db():
        async with TestSession() as session:
            yield session
    return _get_test_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client with mocked auth and DB. Use Authorization header to pick user."""
    from arcticai.api import app
    from arcticai.auth import get_current_user
    from arcticai.db import get_db

    app.dependency_overrides[get_db] = _override_get_db()
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# Convenience auth headers
AUTH_USER1 = {"Authorization": "Bearer token-user1"}
AUTH_USER2 = {"Authorization": "Bearer token-user2"}
AUTH_UNVERIFIED = {"Authorization": "Bearer token-unverified"}
