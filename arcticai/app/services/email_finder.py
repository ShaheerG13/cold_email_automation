from __future__ import annotations

import re

from arcticai.app.schemas.pipeline import CompanyCandidate, ContactCandidate
from arcticai.app.services.hunter_client import HunterNotConfigured, hunter_domain_search


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_RELEVANT_KEYWORDS = ("ceo", "hr", "recruit", "career", "jobs", "talent", "people", "hiring")


def _extract_emails(text: str) -> list[str]:
    return sorted(set(_EMAIL_RE.findall(text)))


def _filter_relevant(emails: list[str]) -> list[str]:
    filtered: list[str] = []
    for e in emails:
        local = e.split("@", 1)[0].lower()
        if any(k in local for k in _RELEVANT_KEYWORDS):
            filtered.append(e)
    return filtered


async def find_relevant_emails(company: CompanyCandidate) -> list[ContactCandidate]:
    if not company.website:
        return []

    domain = company.website.replace("https://", "").replace("http://", "").split("/", 1)[0].strip()
    if not domain or "." not in domain:
        return []

    try:
        api_entries = await hunter_domain_search(domain=domain)
        ceo_like: list[ContactCandidate] = []
        generic_relevant: list[ContactCandidate] = []
        for entry in api_entries:
            email = entry.get("email") or ""
            if not email:
                continue
            position = (entry.get("position") or "").lower()
            local = email.split("@", 1)[0].lower()
            candidate = ContactCandidate(
                email=email,
                role_guess=entry.get("position") or entry.get("department") or None,
                source="api",
            )
            if any(k in position for k in ("ceo", "chief executive", "president", "founder")):
                ceo_like.append(candidate)
            elif any(k in local for k in _RELEVANT_KEYWORDS):
                generic_relevant.append(candidate)

        if ceo_like:
            return ceo_like[:5]
        if generic_relevant:
            return generic_relevant[:5]
    except HunterNotConfigured:
        pass
    except Exception:
        pass

    candidates = [f"ceo@{domain}", f"careers@{domain}", f"hr@{domain}"]
    relevant = _filter_relevant(candidates)
    return [ContactCandidate(email=e, role_guess="careers/hr", source="scrape") for e in relevant]

