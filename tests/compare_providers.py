"""
Side-by-side comparison: old providers (SerpAPI, Hunter) vs new (Google CSE, DIY).

Usage:
    python -m tests.compare_providers

Requires env vars for whichever providers you want to compare:
  Old: SERPAPI_API_KEY, HUNTER_API_KEY
  New: GOOGLE_API_KEY + GOOGLE_CSE_ID  (DIY email finder needs no keys)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from arcticai.services import (
    diy_domain_search,
    hunter_domain_search,
    serper_search,
    serpapi_search,
    scrape_site_emails,
    smtp_verify,
)

# ── Config ──
SEARCH_QUERY = "software companies San Francisco -site:indeed.com -site:linkedin.com -site:glassdoor.com"
TEST_DOMAINS = ["stripe.com", "notion.so", "figma.com", "linear.app", "retool.com"]


def _header(text: str) -> None:
    print(f"\n{'=' * 60}\n  {text}\n{'=' * 60}")


def _sub(text: str) -> None:
    print(f"\n--- {text} ---")


# ── Search comparison ──


async def compare_search() -> None:
    _header("SEARCH COMPARISON")

    serp_results = None
    google_results = None

    # SerpAPI
    if os.getenv("SERPAPI_API_KEY", "").strip():
        _sub("SerpAPI")
        t0 = time.perf_counter()
        try:
            serp_results = await serpapi_search(query=SEARCH_QUERY, num=10)
            elapsed = time.perf_counter() - t0
            print(f"  Results: {len(serp_results)}  ({elapsed:.2f}s)")
            for i, r in enumerate(serp_results, 1):
                title = (r.get("title") or "")[:50]
                link = (r.get("link") or "")[:60]
                print(f"  {i:>2}. {title:<50}  {link}")
        except Exception as e:
            print(f"  ERROR: {e}")
    else:
        print("\n  [SerpAPI] Skipped — SERPAPI_API_KEY not set")

    # Serper.dev
    if os.getenv("SERPER_API_KEY", "").strip():
        _sub("Serper.dev")
        t0 = time.perf_counter()
        try:
            google_results = await serper_search(query=SEARCH_QUERY, num=10)
            elapsed = time.perf_counter() - t0
            print(f"  Results: {len(google_results)}  ({elapsed:.2f}s)")
            for i, r in enumerate(google_results, 1):
                title = (r.get("title") or "")[:50]
                link = (r.get("link") or "")[:60]
                print(f"  {i:>2}. {title:<50}  {link}")
        except Exception as e:
            print(f"  ERROR: {e}")
    else:
        print("\n  [Serper.dev] Skipped — SERPER_API_KEY not set")

    # Overlap analysis
    if serp_results and google_results:
        _sub("Overlap Analysis")
        serp_domains = {r.get("link", "").split("/")[2] if "/" in r.get("link", "") else "" for r in serp_results}
        google_domains = {r.get("link", "").split("/")[2] if "/" in r.get("link", "") else "" for r in google_results}
        serp_domains.discard("")
        google_domains.discard("")
        overlap = serp_domains & google_domains
        print(f"  SerpAPI domains:  {len(serp_domains)}")
        print(f"  Google domains:   {len(google_domains)}")
        print(f"  Overlap:          {len(overlap)}  ({', '.join(sorted(overlap)[:5])})")
        print(f"  Only in SerpAPI:  {', '.join(sorted(serp_domains - google_domains)[:5]) or '(none)'}")
        print(f"  Only in Google:   {', '.join(sorted(google_domains - serp_domains)[:5]) or '(none)'}")


# ── Email comparison ──


async def compare_emails() -> None:
    _header("EMAIL FINDER COMPARISON")

    for domain in TEST_DOMAINS:
        _sub(f"Domain: {domain}")

        # Hunter.io
        if os.getenv("HUNTER_API_KEY", "").strip():
            t0 = time.perf_counter()
            try:
                hunter = await hunter_domain_search(domain=domain)
                elapsed = time.perf_counter() - t0
                print(f"  [Hunter.io]  {len(hunter)} emails  ({elapsed:.2f}s)")
                for e in hunter[:5]:
                    print(f"    {e['email']:<35} {e.get('position', '')}")
            except Exception as e:
                print(f"  [Hunter.io]  ERROR: {e}")
        else:
            print("  [Hunter.io]  Skipped — HUNTER_API_KEY not set")

        # DIY: scrape
        t0 = time.perf_counter()
        try:
            scraped = await scrape_site_emails(domain)
            elapsed = time.perf_counter() - t0
            print(f"  [DIY scrape] {len(scraped)} emails  ({elapsed:.2f}s)")
            for e in scraped[:5]:
                print(f"    {e['email']:<35} {e.get('position', '')}")
        except Exception as e:
            print(f"  [DIY scrape] ERROR: {e}")

        # DIY: full (scrape + patterns + SMTP verify)
        t0 = time.perf_counter()
        try:
            diy = await diy_domain_search(domain=domain)
            elapsed = time.perf_counter() - t0
            print(f"  [DIY full]   {len(diy)} emails  ({elapsed:.2f}s)")
            for e in diy[:5]:
                print(f"    {e['email']:<35} {e.get('position', '')}")
        except Exception as e:
            print(f"  [DIY full]   ERROR: {e}")

        print()


# ── SMTP verification spot check ──


async def test_smtp_verify() -> None:
    _header("SMTP VERIFICATION SPOT CHECK")
    test_emails = [
        "info@stripe.com",
        "careers@stripe.com",
        "nonexistent12345xyz@stripe.com",
        "info@notion.so",
        "hello@linear.app",
    ]
    for email in test_emails:
        result = await smtp_verify(email)
        status = "VALID" if result else "INVALID/UNKNOWN"
        print(f"  {email:<40} → {status}")


async def main() -> None:
    print("ArcticAI Provider Comparison Test")
    print(f"Configured: SERPER={'YES' if os.getenv('SERPER_API_KEY', '').strip() else 'NO'}"
          f"  SERPAPI={'YES' if os.getenv('SERPAPI_API_KEY', '').strip() else 'NO'}"
          f"  HUNTER={'YES' if os.getenv('HUNTER_API_KEY', '').strip() else 'NO'}")

    await compare_search()
    await compare_emails()
    await test_smtp_verify()

    _header("DONE")


if __name__ == "__main__":
    asyncio.run(main())
