from __future__ import annotations

import time

from redis.asyncio import Redis

from arcticai.app.utils.redis_client import get_redis
from arcticai.app.utils.debug_log import dlog


class RateLimitExceeded(Exception):
    pass


async def enforce_daily_limit(*, key: str, max_per_day: int) -> None:
    """
    Enforces a simple UTC-day counter in Redis.
    If REDIS_URL isn't configured, this becomes a no-op (dev-friendly).
    """
    redis: Redis | None = get_redis()
    if redis is None:
        # region agent log
        dlog(
            location="arcticai/app/utils/rate_limit.py:enforce_daily_limit",
            message="redis_not_configured_noop",
            data={"key": key, "max_per_day": max_per_day},
            run_id="pre-fix",
            hypothesis_id="H3",
        )
        # endregion
        return

    day_bucket = int(time.time() // 86400)
    redis_key = f"rl:{key}:{day_bucket}"

    # Atomic-ish for our needs: INCR then set expiry on first hit.
    count = await redis.incr(redis_key)
    if count == 1:
        await redis.expire(redis_key, 2 * 86400)

    if count > max_per_day:
        # region agent log
        dlog(
            location="arcticai/app/utils/rate_limit.py:enforce_daily_limit",
            message="rate_limit_exceeded",
            data={"key": key, "count": count, "max_per_day": max_per_day},
            run_id="pre-fix",
            hypothesis_id="H3",
        )
        # endregion
        raise RateLimitExceeded(f"Daily limit exceeded: {count}/{max_per_day}")

    # region agent log
    dlog(
        location="arcticai/app/utils/rate_limit.py:enforce_daily_limit",
        message="rate_limit_ok",
        data={"key": key, "count": count, "max_per_day": max_per_day},
        run_id="pre-fix",
        hypothesis_id="H3",
    )
    # endregion

