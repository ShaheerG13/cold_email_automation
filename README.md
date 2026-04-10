# ArcticAI: Cold Email Automation SaaS

**- A WORK IN PROGRESS**

(Via Claude Code)

#
ArcticAI automates cold email outreach for job seekers. Search for companies by field and location, find contact emails, generate personalized email drafts via LLM, and send them after review.

**Stack:** Python + FastAPI + Supabase (auth & PostgreSQL) + HTML/CS/JS frontend

## How It Works

1. **Search** — Enter your field, location, and experience. The pipeline discovers relevant companies via Serper.dev
2. **Find Emails** — Click "Find Emails" on companies you want to pursue. Hunter.io finds contacts, and Groq generates a personalized draft
3. **Review & Send** — Edit the draft, approve it, and send via SendGrid (or copy it to send manually)

## Authentication

Authentication is handled entirely by Supabase Auth:

- **Signup/Login/Logout** — Supabase JS SDK on the frontend
- **Email verification** — Supabase sends verification emails, unverified users are blocked from API actions
- **Password reset** — Supabase handles the reset flow
- **JWT validation** — Backend validates Supabase JWTs on every protected request
- **No passwords stored locally** — Supabase manages all credentials

## API Endpoints

All endpoints are under `/api/v1/`. Protected endpoints require `Authorization: Bearer <token>`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/config` | None | Public Supabase config for frontend |
| GET | `/auth/me` | Required | Current user info |
| POST | `/auth/forgot-password` | None | Trigger password reset email |
| POST | `/search` | Verified | Discover companies by field/location |
| POST | `/find-emails` | Verified | Find emails + generate draft for one company |
| GET | `/companies` | Verified | List saved companies |
| POST | `/companies` | Verified | Save a company |
| POST | `/outreach` | Verified | Create outreach draft |
| GET | `/outreach` | Verified | List outreach items |
| PATCH | `/outreach/{id}` | Verified | Edit draft email/subject/body |
| POST | `/outreach/{id}/approve` | Verified | Approve draft for sending |
| POST | `/outreach/{id}/reject` | Verified | Reject draft |
| POST | `/outreach/{id}/send` | Verified | Send via SendGrid |

## Rate Limiting

Per-user daily limits, enforced via Redis

| Endpoint | Free Tier | Pro (5x) |
|----------|-----------|----------|
| Search | 10/day | 50/day |
| Find Emails | 25/day | 125/day |
| Create Outreach | 25/day | 125/day |
| Send Outreach | 10/day | 50/day |

## Testing

```bash
python -m pytest tests/test_api.py -v
```

16 integration tests covering auth, companies, outreach workflow, ownership isolation, and request ID headers. Uses mocked auth and in-memory SQLite.

## Project Structure

```
arcticai/
  api.py          API endpoints, middleware, app factory
  auth.py         Supabase JWT validation, rate limiting
  services.py     Search, email finding, LLM drafts, sending
  models.py       SQLAlchemy models (User, Company, Contact, Outreach)
  schemas.py      Pydantic request/response schemas
  db.py           Async database engine + session factory
  static/
    index.html    Vanilla JS single-page frontend
alembic/          Database migrations
tests/
  test_api.py     Integration tests
```
