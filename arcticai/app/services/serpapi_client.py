from __future__ import annotations

import os

import httpx


class SerpApiNotConfigured(Exception):
    pass


async def serpapi_search(*, query: str, num: int = 10) -> list[dict]:
    api_key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not api_key:
        raise SerpApiNotConfigured("SERPAPI_API_KEY is not set")

    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": num,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("https://serpapi.com/search.json", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("organic_results") or []
    return results

