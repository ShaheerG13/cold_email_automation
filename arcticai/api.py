from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("arcticai")

from arcticai.auth import get_current_user, get_supabase, rate_limit, require_verified
from arcticai.db import get_db
from arcticai.models import Company, Outreach, User
from arcticai.schemas import (
    CompanyCreate,
    CompanyOut,
    FindEmailsRequest,
    ForgotPasswordRequest,
    MessageResponse,
    OutreachActionResponse,
    OutreachCreateRequest,
    OutreachListResponse,
    OutreachResponse,
    OutreachUpdateRequest,
    PipelineResultItem,
    PipelineRunRequest,
    PipelineRunResponse,
    UserOut,
)
from arcticai.services import (
    create_outreach,
    enrich_company_emails,
    list_outreach,
    run_pipeline,
    send_outreach,
    set_outreach_status,
    update_outreach,
)

router = APIRouter(prefix="/api/v1")


async def _get_outreach_owned(outreach_id: int, user: User, db: AsyncSession) -> Outreach:
    """Fetch an outreach row and verify it belongs to the authenticated user."""
    o = await db.get(Outreach, outreach_id)
    if o is None or o.user_id != user.id:
        raise HTTPException(status_code=404, detail="Outreach not found")
    return o


# ── Config (public, no auth) ──

@router.get("/config")
async def config():
    """Return public Supabase config for the frontend."""
    return {
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", ""),
    }


# ── Auth ──

@router.get("/auth/me", response_model=UserOut)
async def auth_me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        is_verified=user.is_verified,
        tier=user.tier,
    )


@router.post("/auth/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest) -> MessageResponse:
    """Send a password-reset email via Supabase Auth."""
    try:
        sb = get_supabase()
        sb.auth.reset_password_email(payload.email)
    except Exception:
        pass  # Don't reveal whether the email exists
    return MessageResponse(message="If that email is registered, a reset link has been sent.")


# ── Search ──

@router.post("/search", response_model=PipelineRunResponse)
async def search(req: PipelineRunRequest, user: User = Depends(require_verified), _rl: User = rate_limit("search", 10)) -> PipelineRunResponse:
    items = await run_pipeline(
        location=req.location,
        field=req.field,
        experience=req.experience,
        target_roles=req.target_roles,
    )
    return PipelineRunResponse(items=items)


@router.post("/find-emails", response_model=PipelineResultItem)
async def find_emails(req: FindEmailsRequest, user: User = Depends(require_verified), _rl: User = rate_limit("find_emails", 25)) -> PipelineResultItem:
    """Find contact emails + generate email draft for a single company."""
    return await enrich_company_emails(
        company_name=req.company_name,
        company_website=req.company_website,
        field=req.field,
        experience=req.experience,
    )


# ── Companies ──

@router.get("/companies", response_model=list[CompanyOut])
async def companies_list(user: User = Depends(require_verified), db: AsyncSession = Depends(get_db)) -> list[CompanyOut]:
    res = await db.execute(select(Company).where(Company.user_id == user.id).order_by(Company.id.desc()).limit(200))
    rows = list(res.scalars().all())
    return [
        CompanyOut(
            id=c.id,
            name=c.name,
            website=c.website,
            location=c.location,
            field=c.field,
            about=c.about,
        )
        for c in rows
    ]


@router.post("/companies", response_model=CompanyOut)
async def companies_create(payload: CompanyCreate, user: User = Depends(require_verified), db: AsyncSession = Depends(get_db)) -> CompanyOut:
    c = Company(
        user_id=user.id,
        name=payload.name,
        website=payload.website,
        location=payload.location,
        field=payload.field,
        about=payload.about,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return CompanyOut(
        id=c.id,
        name=c.name,
        website=c.website,
        location=c.location,
        field=c.field,
        about=c.about,
    )


# ── Outreach ──

@router.post("/outreach", response_model=OutreachResponse)
async def outreach_create(payload: OutreachCreateRequest, user: User = Depends(require_verified), db: AsyncSession = Depends(get_db), _rl: User = rate_limit("outreach_create", 25)) -> OutreachResponse:
    o = await create_outreach(
        db=db,
        user_id=user.id,
        company_name=payload.company_name,
        company_website=payload.company_website,
        to_email=payload.to_email,
        subject=payload.subject,
        body=payload.body,
    )
    return OutreachResponse(
        id=o.id,
        user_id=o.user_id,
        company_id=o.company_id,
        email=o.email,
        message_subject=o.message_subject,
        message_body=o.message_body,
        status=o.status,
    )


@router.get("/outreach", response_model=OutreachListResponse)
async def outreach_list(user: User = Depends(require_verified), db: AsyncSession = Depends(get_db)) -> OutreachListResponse:
    items = await list_outreach(db=db, user_id=user.id)
    return OutreachListResponse(
        items=[
            OutreachResponse(
                id=o.id,
                user_id=o.user_id,
                company_id=o.company_id,
                email=o.email,
                message_subject=o.message_subject,
                message_body=o.message_body,
                status=o.status,
            )
            for o in items
        ]
    )


@router.patch("/outreach/{outreach_id}", response_model=OutreachResponse)
async def outreach_update(outreach_id: int, payload: OutreachUpdateRequest, user: User = Depends(require_verified), db: AsyncSession = Depends(get_db)) -> OutreachResponse:
    await _get_outreach_owned(outreach_id, user, db)
    o = await update_outreach(db=db, outreach_id=outreach_id, to_email=payload.to_email, subject=payload.subject, body=payload.body)
    if not o:
        raise HTTPException(status_code=404, detail="Outreach not found")
    return OutreachResponse(id=o.id, user_id=o.user_id, company_id=o.company_id, email=o.email, message_subject=o.message_subject, message_body=o.message_body, status=o.status)


@router.post("/outreach/{outreach_id}/approve", response_model=OutreachActionResponse)
async def outreach_approve(outreach_id: int, user: User = Depends(require_verified), db: AsyncSession = Depends(get_db)) -> OutreachActionResponse:
    await _get_outreach_owned(outreach_id, user, db)
    o = await set_outreach_status(db=db, outreach_id=outreach_id, status="approved")
    if not o:
        raise HTTPException(status_code=404, detail="Outreach not found")
    return OutreachActionResponse(id=o.id, status=o.status)


@router.post("/outreach/{outreach_id}/reject", response_model=OutreachActionResponse)
async def outreach_reject(outreach_id: int, user: User = Depends(require_verified), db: AsyncSession = Depends(get_db)) -> OutreachActionResponse:
    await _get_outreach_owned(outreach_id, user, db)
    o = await set_outreach_status(db=db, outreach_id=outreach_id, status="rejected")
    if not o:
        raise HTTPException(status_code=404, detail="Outreach not found")
    return OutreachActionResponse(id=o.id, status=o.status)


@router.post("/outreach/{outreach_id}/send", response_model=OutreachActionResponse)
async def outreach_send(outreach_id: int, user: User = Depends(require_verified), db: AsyncSession = Depends(get_db), _rl: User = rate_limit("outreach_send", 10)) -> OutreachActionResponse:
    await _get_outreach_owned(outreach_id, user, db)
    o, outcome = await send_outreach(db=db, outreach_id=outreach_id, sender_email=user.email)
    if o is None:
        raise HTTPException(status_code=404, detail="Outreach not found")
    if outcome == "not_approved":
        raise HTTPException(status_code=409, detail="Outreach must be approved before sending")
    if outcome == "rate_limited":
        raise HTTPException(status_code=429, detail="Daily send limit exceeded")
    if outcome == "send_not_configured":
        raise HTTPException(status_code=501, detail="SendGrid not configured (need SENDGRID_FROM_EMAIL)")
    if outcome != "sent":
        raise HTTPException(status_code=500, detail="Failed to send")
    return OutreachActionResponse(id=o.id, status=o.status, detail="sent")


# ── Middleware ──


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request and log request/response."""

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        logger.info(
            "request_start",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path},
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_end",
            extra={"request_id": request_id, "status": response.status_code},
        )
        return response


# ── Logging setup ──


def _configure_logging() -> None:
    """Set up structured JSON-ish logging for the app."""
    handler = logging.StreamHandler()
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        defaults={"request_id": "-"},
    )
    handler.setFormatter(fmt)
    root = logging.getLogger("arcticai")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


# ── App factory ──

def create_app() -> FastAPI:
    load_dotenv()
    _configure_logging()
    app = FastAPI(title="ArcticAI", version="0.4.0")

    # Middleware (order matters — first added = outermost)
    app.add_middleware(RequestIDMiddleware)

    # CORS
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(router)

    # Static files + index
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(str(static_dir / "index.html"))

    return app


app = create_app()
