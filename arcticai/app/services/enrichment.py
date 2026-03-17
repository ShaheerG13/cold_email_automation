from __future__ import annotations

from arcticai.app.schemas.pipeline import CompanyCandidate


async def enrich_company(company: CompanyCandidate) -> CompanyCandidate:
    # For now, prefer whatever description came from search (snippet),
    # and only fall back to a generic line if nothing is available.
    if not company.about:
        company.about = "No detailed description found yet."
    if not company.keywords:
        company.keywords = []
    return company

