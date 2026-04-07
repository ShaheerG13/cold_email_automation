from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import Client, create_client

from arcticai.db import get_db
from arcticai.models import User


def _supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return create_client(url, key)


_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = _supabase_client()
    return _client


async def get_or_create_user(db: AsyncSession, supabase_uid: str, email: str, name: str, email_confirmed: bool) -> User:
    """Look up local User by supabase_uid. Create on first call."""
    res = await db.execute(select(User).where(User.supabase_uid == supabase_uid))
    user = res.scalar_one_or_none()
    if user:
        # Sync verification status from Supabase
        if user.is_verified != email_confirmed:
            user.is_verified = email_confirmed
            await db.commit()
            await db.refresh(user)
        return user
    user = User(
        supabase_uid=supabase_uid,
        name=name,
        email=email,
        is_verified=email_confirmed,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    authorization: str = Header(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: validate Supabase JWT, return local User."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = authorization.replace("Bearer ", "", 1).strip()
    if not token:
        raise credentials_exception

    try:
        sb = get_supabase()
        resp = sb.auth.get_user(token)
        sb_user = resp.user
        if sb_user is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    email_confirmed = sb_user.email_confirmed_at is not None
    user = await get_or_create_user(
        db=db,
        supabase_uid=sb_user.id,
        email=sb_user.email or "",
        name=sb_user.user_metadata.get("name", "") if sb_user.user_metadata else "",
        email_confirmed=email_confirmed,
    )
    return user


async def require_verified(user: User = Depends(get_current_user)) -> User:
    """Layered dependency: user must have a verified email."""
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your inbox.",
        )
    return user


# ── Rate limiting ──

TIER_MULTIPLIERS: dict[str, int] = {
    "free": 1,
    "pro": 5,
    "enterprise": 20,
}


def rate_limit(action: str, default_limit: int):
    """Return a FastAPI dependency that enforces a daily rate limit per user.

    The actual limit is ``default_limit * tier_multiplier``.
    """
    from arcticai.services import enforce_daily_limit  # avoid circular import

    async def _check(user: User = Depends(require_verified)) -> User:
        multiplier = TIER_MULTIPLIERS.get(user.tier, 1)
        limit = default_limit * multiplier
        try:
            await enforce_daily_limit(key=f"user:{user.id}:{action}", max_per_day=limit)
        except RuntimeError:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily limit exceeded for {action} ({limit}/day on {user.tier} tier)",
            )
        except Exception:
            pass  # Redis unavailable — allow request through
        return user

    return Depends(_check)
