from __future__ import annotations

import os
from functools import lru_cache

from redis.asyncio import Redis


@lru_cache(maxsize=1)
def get_redis() -> Redis | None:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    return Redis.from_url(url, decode_responses=True)

