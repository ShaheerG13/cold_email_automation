from __future__ import annotations

import os

import httpx


class HunterNotConfigured(Exception):
    pass


async def hunter_domain_search(*, domain: str) -> list[dict]:
    api_key = os.getenv("HUNTER_API_KEY", "").strip()
    if not api_key:
        raise HunterNotConfigured("HUNTER_API_KEY is not set")

    params = {"domain": domain, "api_key": api_key}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("https://api.hunter.io/v2/domain-search", params=params)
        r.raise_for_status()
        data = r.json()

    emails: list[dict] = []
    for e in ((data.get("data") or {}).get("emails") or []):
        v = (e.get("value") or "").strip()
        if not v:
            continue
        emails.append(
            {
                "email": v,
                "position": (e.get("position") or "").strip(),
                "department": (e.get("department") or "").strip(),
            }
        )
    return emails

