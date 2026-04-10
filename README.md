# ArcticAI (Cold Email Automation) — Backend Skeleton

**a work in progress**

FastAPI backend

User input → company discovery → enrichment → email discovery → AI draft generation → user approval → send

## Run (dev)

Create a virtualenv, then install deps:

```bash
python -m venv venv
\venv\Scripts\activate
pip install -r requirements.txt
```

Optional: copy env vars:

```bash
copy .env.example .env
```

Start the API:

```bash
uvicorn arcticai.app.main:app --reload
```

By default it uses SQLite (`/arcticai.db`) if `DATABASE_URL` is not set.

## API

- `POST /search`: runs the pipeline and returns companies + contacts + a draft (does not send yet)
- `POST /outreach`: create a pending outreach draft in DB
- `POST /outreach/{id}/approve`: mark draft as approved
- `POST /outreach/{id}/send`: attempts send (enforces rate limit; currently returns 501 until SendGrid/Gmail is wired)
- `GET /outreach?user_id=...`: list outreach for a user

## Safety Defaults

- No auto-send anywhere.
- `send_email()` is currently intentionally stubbed and raises unless configured.
- Rate limit uses Redis if `REDIS_URL` is set (otherwise no-op for local dev).
