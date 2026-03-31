from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arcticai.db import engine, get_db
from arcticai.models import Base, Company
from arcticai.schemas import (
    CompanyCreate,
    CompanyOut,
    OutreachActionResponse,
    OutreachCreateRequest,
    OutreachListResponse,
    OutreachResponse,
    PipelineRunRequest,
    PipelineRunResponse,
)
from arcticai.services import create_outreach, list_outreach, run_pipeline, send_outreach, set_outreach_status


def create_app() -> FastAPI:
    load_dotenv()
    app = FastAPI(title="ArcticAI", version="0.2.0")

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(str(static_dir / "index.html"))

    @app.on_event("startup")
    async def startup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @app.post("/search", response_model=PipelineRunResponse)
    async def search(req: PipelineRunRequest) -> PipelineRunResponse:
        items = await run_pipeline(
            location=req.location,
            field=req.field,
            experience=req.experience,
            target_roles=req.target_roles,
        )
        return PipelineRunResponse(items=items)

    # Companies (DB-backed)
    @app.get("/companies", response_model=list[CompanyOut])
    async def companies_list(db: AsyncSession = Depends(get_db)) -> list[CompanyOut]:
        res = await db.execute(select(Company).order_by(Company.id.desc()).limit(200))
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

    @app.post("/companies", response_model=CompanyOut)
    async def companies_create(payload: CompanyCreate, db: AsyncSession = Depends(get_db)) -> CompanyOut:
        c = Company(
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

    # Outreach flow
    @app.post("/outreach", response_model=OutreachResponse)
    async def outreach_create(payload: OutreachCreateRequest, db: AsyncSession = Depends(get_db)) -> OutreachResponse:
        o = await create_outreach(
            db=db,
            user_id=payload.user_id,
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

    @app.get("/outreach", response_model=OutreachListResponse)
    async def outreach_list(user_id: int = Query(...), db: AsyncSession = Depends(get_db)) -> OutreachListResponse:
        items = await list_outreach(db=db, user_id=user_id)
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

    @app.post("/outreach/{outreach_id}/approve", response_model=OutreachActionResponse)
    async def outreach_approve(outreach_id: int, db: AsyncSession = Depends(get_db)) -> OutreachActionResponse:
        o = await set_outreach_status(db=db, outreach_id=outreach_id, status="approved")
        if not o:
            raise HTTPException(status_code=404, detail="Outreach not found")
        return OutreachActionResponse(id=o.id, status=o.status)

    @app.post("/outreach/{outreach_id}/reject", response_model=OutreachActionResponse)
    async def outreach_reject(outreach_id: int, db: AsyncSession = Depends(get_db)) -> OutreachActionResponse:
        o = await set_outreach_status(db=db, outreach_id=outreach_id, status="rejected")
        if not o:
            raise HTTPException(status_code=404, detail="Outreach not found")
        return OutreachActionResponse(id=o.id, status=o.status)

    @app.post("/outreach/{outreach_id}/send", response_model=OutreachActionResponse)
    async def outreach_send(outreach_id: int, db: AsyncSession = Depends(get_db)) -> OutreachActionResponse:
        o, outcome = await send_outreach(db=db, outreach_id=outreach_id)
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

    return app


app = create_app()

