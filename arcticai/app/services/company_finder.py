from __future__ import annotations

from arcticai.app.schemas.pipeline import CompanyCandidate
from arcticai.app.services.serpapi_client import SerpApiNotConfigured, serpapi_search


async def find_companies(location: str, field: str) -> list[CompanyCandidate]:
    query_hint = f"{field} companies in {location}"
    try:
        results = await serpapi_search(query=query_hint, num=10)
        companies: list[CompanyCandidate] = []
        for r in results:
            title = (r.get("title") or "").strip()
            link = (r.get("link") or "").strip()
            snippet = (r.get("snippet") or "").strip()
            if not link:
                continue
            host = link.replace("https://", "").replace("http://", "").split("/", 1)[0]
            host_main = host.split(":")[0]
            parts = [p for p in host_main.split(".") if p and p.lower() not in ("www", "www2")]
            base_name = parts[-2] if len(parts) >= 2 else (parts[0] if parts else host_main)
            name = base_name.capitalize()
            companies.append(
                CompanyCandidate(
                    name=name,
                    website=link or None,
                    about=snippet or None,
                    keywords=[query_hint],
                )
            )
        if companies:
            # Limit to top 5 for usability.
            return companies[:5]
    except SerpApiNotConfigured:
        pass
    except Exception:
        # If SerpAPI fails transiently, fall back to deterministic examples.
        pass

    return [
        CompanyCandidate(name="Example Security Co", website="https://example.com", keywords=[query_hint]),
        CompanyCandidate(name="Local IT Services LLC", website="https://example.org", keywords=[query_hint]),
    ]

