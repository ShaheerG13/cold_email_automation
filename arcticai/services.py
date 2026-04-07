from __future__ import annotations

import asyncio
import os
import re
import smtplib
import time
from concurrent.futures import ThreadPoolExecutor

import dns.resolver
import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arcticai.models import Company, Outreach
from arcticai.schemas import CompanyCandidate, ContactCandidate, EmailDraft, PipelineResultItem


def _redis() -> Redis | None:
    url = os.getenv("REDIS_URL", "").strip()
    return Redis.from_url(url, decode_responses=True) if url else None


async def enforce_daily_limit(*, key: str, max_per_day: int) -> None:
    r = _redis()
    if r is None:
        return
    day_bucket = int(time.time() // 86400)
    redis_key = f"rl:{key}:{day_bucket}"
    try:
        count = await r.incr(redis_key)
        if count == 1:
            await r.expire(redis_key, 2 * 86400)
    finally:
        await r.aclose()
    if count > max_per_day:
        raise RuntimeError("Daily send limit exceeded")


async def serper_search(*, query: str, num: int = 10) -> list[dict]:
    """Search via Serper.dev — returns Google results.

    2,500 free queries (no CC), then $1/1k pay-as-you-go.
    """
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SERPER_API_KEY not set")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num},
        )
        r.raise_for_status()
        return r.json().get("organic") or []


async def serpapi_search(*, query: str, num: int = 10) -> list[dict]:
    """Legacy: SerpAPI search. Kept as fallback."""
    api_key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SERPAPI_API_KEY not set")
    params = {"engine": "google", "q": query, "api_key": api_key, "num": num}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("https://serpapi.com/search.json", params=params)
        r.raise_for_status()
        return r.json().get("organic_results") or []


async def web_search(*, query: str, num: int = 10) -> list[dict]:
    """Unified search: tries Serper first, falls back to SerpAPI."""
    try:
        return await serper_search(query=query, num=num)
    except RuntimeError:
        return await serpapi_search(query=query, num=num)


_AGGREGATOR_DOMAINS: frozenset[str] = frozenset({
    "indeed.com", "linkedin.com", "glassdoor.com", "monster.com",
    "ziprecruiter.com", "careerbuilder.com", "simplyhired.com",
    "crunchbase.com", "bloomberg.com", "yelp.com", "yellowpages.com",
    "facebook.com", "twitter.com", "instagram.com", "wikipedia.org",
    "bbb.org", "manta.com", "dnb.com", "zoominfo.com", "owler.com",
    "craft.co", "pitchbook.com", "angel.co", "wellfound.com",
    "comparably.com", "vault.com", "theladders.com", "dice.com",
    "flexjobs.com", "salary.com", "payscale.com", "devitjobs.com",
    "remote.co", "weworkremotely.com", "remoteok.com", "himalayas.app",
    "otta.com", "levels.fyi", "teamblind.com",
})

# Subdomains that indicate a careers/jobs page of a real company (not the company itself)
_CAREER_SUBDOMAINS: frozenset[str] = frozenset({
    "careers", "jobs", "job", "hire", "hiring", "work", "apply",
    "talent", "recruit", "join", "workday", "greenhouse", "lever",
})

# SLD keywords that indicate a job board rather than a real company
_JOB_BOARD_KEYWORDS: frozenset[str] = frozenset({
    "job", "jobs", "career", "careers", "recruit", "recruiting",
    "staffing", "hiring", "talent", "work", "employ", "employment",
    "builtin",  # catches builtinsf.com, builtinnyc.com, etc.
})

# Separators commonly used in page titles to divide brand from tagline
_TITLE_SEPARATORS = (" | ", " - ", " – ", " — ", " · ", " • ", ": ", " :: ")

# Known large companies to exclude (too big to cold-email for internships)
_LARGE_COMPANY_NAMES: frozenset[str] = frozenset({
    "google", "alphabet", "uber", "lyft", "meta", "facebook", "apple",
    "amazon", "microsoft", "netflix", "salesforce", "oracle", "ibm",
    "intel", "qualcomm", "nvidia", "adobe", "twitter", "x",
    "airbnb", "doordash", "instacart", "stripe", "square", "block",
    "palantir", "snowflake", "databricks", "confluent",
})

# Title tokens that signal a job-board page rather than a company homepage
_TITLE_NOISE_TOKENS: frozenset[str] = frozenset({
    "jobs", "careers", "apply now", "job listings",
    "open positions", "work at", "join our team",
})

# "Name (domain.tld)" — e.g. "Osmosis (osmosis.ai)"
_RE_NAME_DOMAIN = re.compile(
    r"([A-Z][A-Za-z0-9 &'\-\.]{1,40}?)\s+\(([a-z0-9\-]+\.[a-z]{2,})\)"
)
# Bare domain mentions in prose — e.g. "alarm.com", "yext.io"
_RE_BARE_DOMAIN = re.compile(
    r"\b([A-Za-z][A-Za-z0-9\-]{0,30})\.(com|io|ai|co|net|org|app|tech)\b",
    re.IGNORECASE,
)
# Titles that indicate a list/directory page regardless of domain
_RE_LIST_TITLE = re.compile(
    r"^\d+\s+\w"
    r"|^(?:top|best|leading|fastest)[- ]\d+"
    r"|^(?:top|best|leading)\s+\w+\s+(?:companies|startups?|firms?|employers?)"
    r"|\blist\s+of\b"
    r"|\bcompanies?\s+to\s+(?:watch|work\s+for|know)\b",
    re.IGNORECASE,
)

# Words that look like company names in isolation but aren't
_STOP_NAMES: frozenset[str] = frozenset({
    "go", "do", "be", "it", "at", "in", "of", "to", "for", "and", "or",
    "the", "inc", "llc", "corp", "ltd", "co", "new", "big", "top", "best",
    "fast", "good", "great", "free", "open", "first", "last", "next",
    "list", "read", "find", "see", "now", "more", "many", "most", "here",
    "startup", "startups", "company", "companies", "tech", "software",
    "remote", "local", "global", "national", "federal", "group", "team",
})


def _strip_host(url: str) -> str:
    """Return lowercased host without scheme or port."""
    host = url.replace("https://", "").replace("http://", "").split("/", 1)[0]
    return host.split(":")[0].lower()


def _extract_domain(url: str) -> str:
    """Return the registrable domain (no www/www2 prefix)."""
    host = _strip_host(url)
    if host.startswith("www2."):
        host = host[5:]
    elif host.startswith("www."):
        host = host[4:]
    return host


def _base_domain(url: str) -> str:
    """Strip recognised career subdomains to get the parent company domain."""
    host = _strip_host(url)
    parts = host.split(".")
    # e.g. careers.hpe.com → hpe.com
    if len(parts) > 2 and parts[0] in _CAREER_SUBDOMAINS:
        host = ".".join(parts[1:])
    # strip www after potential subdomain removal
    if host.startswith("www."):
        host = host[4:]
    return host


def _homepage(url: str) -> str:
    """Return the company homepage (scheme + base domain, career subdomains resolved)."""
    scheme = "https://" if url.startswith("https") else "http://"
    return f"{scheme}{_base_domain(url)}"


def _is_aggregator(url: str) -> bool:
    domain = _base_domain(url)
    # Explicit blocklist
    if any(domain == d or domain.endswith("." + d) for d in _AGGREGATOR_DOMAINS):
        return True
    parts = domain.split(".")
    tld = parts[-1] if parts else ""
    sld = parts[-2] if len(parts) >= 2 else parts[0] if parts else ""
    # .jobs TLD (e.g. startup.jobs)
    if tld == "jobs":
        return True
    # SLD contains a job-board keyword (e.g. devitjobs.com, builtinsf.com)
    if any(kw in sld for kw in _JOB_BOARD_KEYWORDS):
        return True
    return False


def _name_from_title(title: str, fallback_url: str) -> str:
    """Extract company name from a page title, falling back to domain if needed."""
    if title:
        for sep in _TITLE_SEPARATORS:
            if sep in title:
                candidate = title.split(sep)[0].strip()
                if candidate:
                    return candidate
        if title.strip():
            return title.strip()
    # Fallback: capitalise the SLD of the base domain (e.g. careers.hpe.com → Hpe)
    domain = _base_domain(fallback_url)
    parts = domain.split(".")
    base = parts[-2] if len(parts) >= 2 else (parts[0] if parts else domain)
    return base.capitalize() if base else "Unknown"


# Only exclude sites whose snippets are job descriptions (not useful for name extraction).
# Article sites, Reddit, directories etc. are intentionally allowed — their snippets
# contain company names which we mine directly.
_MINE_EXCLUSIONS = " ".join(
    f"-site:{d}"
    for d in ("indeed.com", "linkedin.com", "glassdoor.com",
              "ziprecruiter.com", "monster.com", "wikipedia.org")
)
_DISCOVERY_QUERY = "{field} companies {location} " + _MINE_EXCLUSIONS


def _is_large_company(name: str) -> bool:
    return name.lower().strip() in _LARGE_COMPANY_NAMES


def _is_title_noise(title: str) -> bool:
    t = title.lower()
    return any(tok in t for tok in _TITLE_NOISE_TOKENS)


def _is_list_title(title: str) -> bool:
    return bool(_RE_LIST_TITLE.search(title))


def _mine_snippet(snippet: str) -> list[tuple[str, str | None]]:
    """
    Extract (name, domain_or_None) from any snippet format:
    structured directories, Reddit-style prose, comma lists, bullet lists.
    """
    results: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    # Pass 1: "Name (domain.tld)" — structured directories e.g. f6s, YC lists
    for m in _RE_NAME_DOMAIN.finditer(snippet):
        name, domain = m.group(1).strip(), m.group(2).strip().lower()
        if name.lower() not in seen:
            seen.add(name.lower())
            results.append((name, domain))

    # Pass 2: bare domain mentions — "alarm.com", "yext.io"
    for m in _RE_BARE_DOMAIN.finditer(snippet):
        domain = m.group(0).lower()
        sld = m.group(1)
        name = sld.capitalize()
        low = name.lower()
        if low not in seen and low not in _STOP_NAMES:
            seen.add(low)
            results.append((name, domain))

    # Pass 3: comma and bullet-separated proper nouns — Reddit/article prose
    for raw in re.split(r"[,·•]", snippet):
        part = raw.strip().strip("\"'()")
        if not part or not part[0].isupper():
            continue
        # Match one or more consecutive capitalised words (handles "Fast Enterprises", "WillowTree")
        m = re.match(
            r"^([A-Z][A-Za-z0-9&'\-]{0,30}(?:\s+[A-Z][A-Za-z0-9&'\-]{0,30}){0,3})",
            part,
        )
        if not m:
            continue
        name = m.group(1).strip()
        low = name.lower()
        if len(name) < 2 or low in seen or low in _STOP_NAMES:
            continue
        seen.add(low)
        results.append((name, None))

    return results


def _domain_to_homepage(domain: str) -> str:
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return f"https://{domain}"


async def _resolve_name_to_homepage(name: str, field: str) -> str | None:
    """Individual company search (num=3) to find a specific company's homepage."""
    try:
        results = await web_search(query=f'"{name}" {field} company', num=3)
    except Exception:
        return None
    for r in results:
        link = (r.get("link") or "").strip()
        if link and not _is_aggregator(link) and not _is_list_title(r.get("title") or ""):
            return _homepage(link)
    return None


async def find_companies(*, location: str, field: str) -> list[CompanyCandidate]:
    kw = f"{field} {location}"
    query = _DISCOVERY_QUERY.format(field=field, location=location)
    try:
        results = await web_search(query=query, num=10)
    except Exception:
        return [CompanyCandidate(name="Example", website="https://example.com",
                                 about=None, keywords=[kw])]

    # Phase 1: mine company names from every result's snippet.
    # Articles, Reddit posts, directories — all are treated as text corpora.
    pool_with_domain: list[tuple[str, str]] = []   # (name, homepage_url)
    pool_name_only: list[str] = []                  # names with no URL yet
    seen_domains: set[str] = set()
    seen_names: set[str] = set()

    for r in results:
        link = (r.get("link") or "").strip()
        if not link:
            continue
        snippet = (r.get("snippet") or "").strip()
        title = (r.get("title") or "").strip()

        # Skip job-listing pages — their snippets describe a role, not companies
        if _is_title_noise(title):
            continue

        # If the result itself is a company homepage, add it directly
        if not _is_aggregator(link) and not _is_list_title(title):
            name = _name_from_title(title, link)
            domain = _extract_domain(link)
            if (not _is_large_company(name)
                    and name.lower() not in seen_names
                    and domain not in seen_domains):
                seen_names.add(name.lower())
                seen_domains.add(domain)
                pool_with_domain.append((name, _homepage(link)))

        # Mine the snippet regardless — even a company's own page may mention others
        for name, domain in _mine_snippet(snippet):
            if _is_large_company(name) or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                pool_with_domain.append((name, _domain_to_homepage(domain)))
            elif not domain:
                pool_name_only.append(name)

    # Phase 2: build output — names with known URLs first (no extra API call needed)
    out: list[CompanyCandidate] = []
    for name, url in pool_with_domain:
        if len(out) >= 5:
            break
        out.append(CompanyCandidate(name=name, website=url, about=None, keywords=[kw]))

    # Phase 3: for remaining slots, search for each company individually.
    # This is now the primary URL-finding mechanism, not a fallback.
    if len(out) < 5 and pool_name_only:
        budget = min(5, 5 - len(out))
        resolved: set[str] = set()
        for name in pool_name_only:
            if len(out) >= 5 or budget <= 0:
                break
            homepage = await _resolve_name_to_homepage(name, field)
            budget -= 1
            if homepage:
                domain = _extract_domain(homepage)
                if domain not in seen_domains:
                    seen_domains.add(domain)
                    resolved.add(name.lower())
                    out.append(CompanyCandidate(name=name, website=homepage, about=None, keywords=[kw]))

        # Last resort: include name-only entries so the user still sees the company
        for name in pool_name_only:
            if len(out) >= 5:
                break
            if name.lower() in resolved or name.lower() in {c.name.lower() for c in out}:
                continue
            out.append(CompanyCandidate(name=name, website=None, about=None, keywords=[kw]))

    return out or [CompanyCandidate(name="Example", website="https://example.com",
                                    about=None, keywords=[kw])]


async def enrich_company(company: CompanyCandidate) -> CompanyCandidate:
    if not company.about:
        company.about = "No detailed description found yet."
    return company


async def hunter_domain_search(*, domain: str) -> list[dict]:
    api_key = os.getenv("HUNTER_API_KEY", "").strip()
    if not api_key:
        return []
    params = {"domain": domain, "api_key": api_key}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("https://api.hunter.io/v2/domain-search", params=params)
        r.raise_for_status()
        data = r.json()
    entries = []
    for e in ((data.get("data") or {}).get("emails") or []):
        email = (e.get("value") or "").strip()
        if not email:
            continue
        entries.append(
            {
                "email": email,
                "position": (e.get("position") or "").strip(),
                "department": (e.get("department") or "").strip(),
            }
        )
    return entries


# ── DIY email finder (replaces Hunter.io) ──

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_JUNK_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "svg", "css", "js", "woff", "woff2", "ttf", "webp"})
_CONTACT_PATHS = ("/contact", "/contact-us", "/about", "/about-us", "/team", "/our-team")

_GENERIC_LOCALS = [
    ("info", "General Contact"),
    ("contact", "General Contact"),
    ("hello", "General Contact"),
    ("team", "General Contact"),
    ("hiring", "Hiring"),
    ("careers", "Hiring"),
    ("jobs", "Hiring"),
    ("hr", "HR"),
    ("talent", "Hiring"),
    ("admin", "Admin"),
    ("office", "Office"),
    ("sales", "Sales"),
]

_smtp_pool = ThreadPoolExecutor(max_workers=4)


def _guess_role_from_local(local: str) -> str:
    low = local.lower()
    for pattern, role in _GENERIC_LOCALS:
        if pattern == low:
            return role
    if low in ("ceo", "founder", "president"):
        return "CEO / Founder"
    if low in ("cto", "vp.engineering"):
        return "CTO"
    return ""


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a single page, return HTML or empty string on failure."""
    try:
        r = await client.get(url)
        return r.text if r.status_code == 200 else ""
    except Exception:
        return ""


async def scrape_site_emails(domain: str) -> list[dict]:
    """Fetch a company's homepage + contact pages and extract email addresses."""
    found: dict[str, str] = {}  # email -> guessed role
    urls = [f"https://{domain}"] + [f"https://{domain}{p}" for p in _CONTACT_PATHS]

    async with httpx.AsyncClient(
        timeout=6, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ArcticAI/1.0)"},
    ) as client:
        # Fetch all pages in parallel
        pages = await asyncio.gather(*(_fetch_page(client, u) for u in urls))
        for html in pages:
            if not html:
                continue
            for raw in _EMAIL_RE.findall(html):
                email = raw.lower()
                ext = email.rsplit(".", 1)[-1]
                if ext in _JUNK_EXTENSIONS:
                    continue
                if email.endswith(f"@{domain}") or email.endswith(f"@www.{domain}"):
                    local = email.split("@")[0]
                    if email not in found:
                        found[email] = _guess_role_from_local(local)

    return [{"email": e, "position": role, "department": ""} for e, role in found.items()]


def _smtp_verify_sync(email: str) -> bool:
    """Synchronous SMTP RCPT TO check — runs in thread pool."""
    domain = email.split("@")[1]
    try:
        answers = dns.resolver.resolve(domain, "MX")
        mx_host = str(sorted(answers, key=lambda r: r.preference)[0].exchange).rstrip(".")
    except Exception:
        return False
    try:
        with smtplib.SMTP(mx_host, 25, timeout=5) as srv:
            srv.ehlo("arcticai.com")
            srv.mail("noreply@arcticai.com")
            code, _ = srv.rcpt(email)
            return code == 250
    except Exception:
        return False


async def smtp_verify(email: str) -> bool:
    """Async wrapper around SMTP verification."""
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_smtp_pool, _smtp_verify_sync, email), timeout=8,
        )
    except (asyncio.TimeoutError, Exception):
        return False


async def diy_domain_search(*, domain: str) -> list[dict]:
    """Free replacement for hunter_domain_search.

    1. Scrape the company website for visible email addresses.
    2. Generate common pattern emails (info@, hiring@, etc.).
    3. Best-effort SMTP verification to filter invalid addresses.

    Returns same shape as hunter_domain_search: list of {email, position, department}.
    """
    # Step 1: scrape
    scraped = await scrape_site_emails(domain)

    # Step 2: generate common patterns (skip if already found via scraping)
    scraped_addrs = {e["email"] for e in scraped}
    patterns = []
    for local, role in _GENERIC_LOCALS:
        addr = f"{local}@{domain}"
        if addr not in scraped_addrs:
            patterns.append({"email": addr, "position": role, "department": ""})

    # Step 3: SMTP-verify everything in parallel (best-effort)
    all_candidates = scraped + patterns
    if all_candidates:
        checks = await asyncio.gather(
            *(smtp_verify(e["email"]) for e in all_candidates),
            return_exceptions=True,
        )
        verified = [e for e, ok in zip(all_candidates, checks) if ok is True]
        # If SMTP verification worked for at least some, prefer verified results
        if verified:
            return verified

    # Fallback: return scraped emails (trusted) + top patterns (unverified)
    return scraped if scraped else patterns[:5]


_JUNK_LOCALS = frozenset({"noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster"})


async def find_emails(*, domain: str) -> list[dict]:
    """Unified email finder: Hunter primary, DIY fallback."""
    try:
        results = await hunter_domain_search(domain=domain)
        # Filter out useless addresses like noreply@
        results = [e for e in results if e.get("email", "").split("@")[0].lower() not in _JUNK_LOCALS]
        if results:
            return results
    except Exception:
        pass
    return await diy_domain_search(domain=domain)


async def find_relevant_emails(company: CompanyCandidate) -> list[ContactCandidate]:
    if not company.website:
        return []
    domain = company.website.replace("https://", "").replace("http://", "").split("/", 1)[0].split(":")[0].strip()
    if not domain or "." not in domain:
        return []
    try:
        entries = await find_emails(domain=domain)
    except Exception:
        entries = []
    ceo_like: list[ContactCandidate] = []
    other: list[ContactCandidate] = []
    for entry in entries:
        email = entry.get("email") or ""
        pos = (entry.get("position") or "").lower()
        if any(k in pos for k in ("ceo", "chief executive", "president", "founder")):
            ceo_like.append(ContactCandidate(email=email, role_guess=entry.get("position") or None, source="api"))
        else:
            other.append(ContactCandidate(email=email, role_guess=entry.get("position") or entry.get("department") or None, source="api"))
    if ceo_like:
        return ceo_like[:5]
    if other:
        return other[:5]
    return [ContactCandidate(email=f"hiring@{domain}", role_guess="hiring team", source="scrape")]


async def groq_chat(*, prompt: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return ""
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip() or "llama-3.1-8b-instant"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You write concise, professional cold emails. Output plain text only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 350,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    return (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


async def generate_email_draft(*, user_experience: str, target_field: str, company_name: str, company_about: str) -> EmailDraft:
    prompt = f"""
Write a concise cold email (max 120 words).

Candidate experience:
{user_experience}

Company:
{company_name}
About:
{company_about}

Role interest:
{target_field}

Constraints:
- Confident but not pushy
- Personalized
- Include a gentle opt-out line
- Output email body only (no subject line)
""".strip()
    subject = f"Interest in {target_field} opportunities at {company_name}"
    body = await groq_chat(prompt=prompt)
    if not body:
        body = f"Hi {company_name} hiring team —\n\nI’m interested in {target_field} roles. Quick background: {user_experience}\n\nOpen to a quick chat?\n\nBest,\n<Your Name>\n\n—\nIf this isn’t relevant, feel free to ignore and I won’t follow up."
    return EmailDraft(subject=subject, body=body, include_unsubscribe_line=True)


async def run_pipeline(*, location: str, field: str, experience: str, target_roles: list[str]) -> list[PipelineResultItem]:
    companies = await find_companies(location=location, field=field)
    items: list[PipelineResultItem] = []
    for c in companies:
        enriched = await enrich_company(c)
        contacts = await find_relevant_emails(enriched)
        draft = await generate_email_draft(
            user_experience=experience,
            target_field=field,
            company_name=enriched.name,
            company_about=enriched.about or "",
        )
        items.append(PipelineResultItem(company=enriched, contacts=contacts, draft=draft))
    return items


async def create_outreach(*, db: AsyncSession, user_id: int, company_name: str, company_website: str | None, to_email: str, subject: str, body: str) -> Outreach:
    company = Company(user_id=user_id, name=company_name, website=company_website)
    db.add(company)
    await db.flush()
    outreach = Outreach(
        user_id=user_id,
        company_id=company.id,
        email=to_email,
        message_subject=subject,
        message_body=body,
        status="pending",
    )
    db.add(outreach)
    await db.commit()
    await db.refresh(outreach)
    return outreach


async def list_outreach(*, db: AsyncSession, user_id: int) -> list[Outreach]:
    res = await db.execute(select(Outreach).where(Outreach.user_id == user_id).order_by(Outreach.id.desc()))
    return list(res.scalars().all())


async def update_outreach(*, db: AsyncSession, outreach_id: int, to_email: str | None, subject: str | None, body: str | None) -> Outreach | None:
    o = await db.get(Outreach, outreach_id)
    if not o:
        return None
    if to_email is not None:
        o.email = to_email
    if subject is not None:
        o.message_subject = subject
    if body is not None:
        o.message_body = body
    await db.commit()
    await db.refresh(o)
    return o


async def set_outreach_status(*, db: AsyncSession, outreach_id: int, status: str) -> Outreach | None:
    o = await db.get(Outreach, outreach_id)
    if not o:
        return None
    o.status = status
    await db.commit()
    await db.refresh(o)
    return o


async def send_email_sendgrid(*, to_email: str, subject: str, body: str, from_email: str) -> None:
    api_key = os.getenv("SENDGRID_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SendGrid not configured (need SENDGRID_API_KEY)")

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.sendgrid.com/v3/mail/send", headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"SendGrid error: {r.status_code} {r.text}")


async def send_outreach(*, db: AsyncSession, outreach_id: int, sender_email: str) -> tuple[Outreach | None, str]:
    o = await db.get(Outreach, outreach_id)
    if not o:
        return None, "not_found"
    if o.status != "approved":
        return o, "not_approved"
    try:
        await enforce_daily_limit(key=f"user:{o.user_id}:send", max_per_day=5)
    except Exception:
        return o, "rate_limited"

    try:
        await send_email_sendgrid(
            to_email=o.email,
            subject=o.message_subject,
            body=o.message_body,
            from_email=sender_email,
        )
    except Exception as e:
        msg = str(e).lower()
        if "not configured" in msg:
            return o, "send_not_configured"
        o.status = "failed"
        await db.commit()
        await db.refresh(o)
        return o, "failed"
    o.status = "sent"
    await db.commit()
    await db.refresh(o)
    return o, "sent"

