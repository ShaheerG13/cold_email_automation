from __future__ import annotations

from arcticai.app.schemas.pipeline import EmailDraft
from arcticai.app.services.groq_client import GroqNotConfigured, groq_chat


async def generate_email_draft(
    *,
    user_experience: str,
    target_field: str,
    company_name: str,
    company_about: str,
) -> EmailDraft:
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
- Output email body only (no subject line)
""".strip()

    subject = f"Interest in {target_field} opportunities at {company_name}"
    body: str
    try:
        body = await groq_chat(prompt=prompt)
        if not body:
            raise RuntimeError("Empty Groq response")
    except GroqNotConfigured:
        body = (
            f"Hi there —\n\n"
            f"I'm reaching out because I'm interested in {target_field} roles and noticed {company_name}.\n"
            f"{company_about.strip()}\n\n"
            f"Quick background: {user_experience.strip()}\n\n"
            f"If you're open to it, I’d love to share a short resume and ask a couple questions about your team.\n\n"
            f"Best,\n"
            f"<Your Name>\n\n"
        )
    except Exception:
        body = (
            f"Hi there —\n\n"
            f"I'm reaching out because I'm interested in {target_field} roles and noticed {company_name}.\n"
            f"{company_about.strip()}\n\n"
            f"Quick background: {user_experience.strip()}\n\n"
            f"If you're open to it, I’d love to share a short resume and ask a couple questions about your team.\n\n"
            f"Best,\n"
            f"<Your Name>\n\n"
        )
    return EmailDraft(subject=subject, body=body, include_unsubscribe_line=True)

