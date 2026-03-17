from __future__ import annotations

import os

import httpx


class GroqNotConfigured(Exception):
    pass


async def groq_chat(*, prompt: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise GroqNotConfigured("GROQ_API_KEY is not set")

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

    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    return content

