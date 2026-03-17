from __future__ import annotations

import os

import httpx


class SendNotConfigured(Exception):
    pass


async def send_email(*, to: str, subject: str, body: str) -> None:
    """
    Send email via SendGrid v3 if SENDGRID_API_KEY is configured.
    (We intentionally do NOT support raw SMTP.)
    """
    api_key = os.getenv("SENDGRID_API_KEY", "").strip()
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "").strip()
    if not api_key or not from_email:
        raise SendNotConfigured("SendGrid not configured (need SENDGRID_API_KEY and SENDGRID_FROM_EMAIL)")

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.sendgrid.com/v3/mail/send", headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"SendGrid error: {r.status_code} {r.text}")

