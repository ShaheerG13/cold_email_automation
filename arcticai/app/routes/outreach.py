from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from arcticai.app.schemas.pipeline import PipelineRunRequest, PipelineRunResponse
from arcticai.app.schemas.outreach import (
    OutreachActionResponse,
    OutreachCreateRequest,
    OutreachListResponse,
    OutreachResponse,
)
from arcticai.app.db.session import get_db
from arcticai.app.services.pipeline import run_pipeline
from arcticai.app.services.outreach_service import create_outreach, list_outreach, send_outreach, set_status

router = APIRouter()


@router.post("/search", response_model=PipelineRunResponse)
async def search_companies(request: PipelineRunRequest) -> PipelineRunResponse:
    # Approval-first flow: this only generates drafts and stores nothing yet.
    return await run_pipeline(request)


@router.post("/outreach", response_model=OutreachResponse)
async def create_outreach_draft(
    request: OutreachCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> OutreachResponse:
    o = await create_outreach(
        db=db,
        user_id=request.user_id,
        company_name=request.company_name,
        company_website=request.company_website,
        to_email=request.to_email,
        subject=request.subject,
        body=request.body,
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
async def get_outreach(
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
) -> OutreachListResponse:
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


@router.post("/outreach/{outreach_id}/approve", response_model=OutreachActionResponse)
async def approve_outreach(
    outreach_id: int,
    db: AsyncSession = Depends(get_db),
) -> OutreachActionResponse:
    o = await set_status(db=db, outreach_id=outreach_id, status="approved")
    if o is None:
        raise HTTPException(status_code=404, detail="Outreach not found")
    return OutreachActionResponse(id=o.id, status=o.status)


@router.post("/outreach/{outreach_id}/reject", response_model=OutreachActionResponse)
async def reject_outreach(
    outreach_id: int,
    db: AsyncSession = Depends(get_db),
) -> OutreachActionResponse:
    o = await set_status(db=db, outreach_id=outreach_id, status="rejected")
    if o is None:
        raise HTTPException(status_code=404, detail="Outreach not found")
    return OutreachActionResponse(id=o.id, status=o.status)


@router.post("/outreach/{outreach_id}/send", response_model=OutreachActionResponse)
async def send_outreach_email(
    outreach_id: int,
    db: AsyncSession = Depends(get_db),
) -> OutreachActionResponse:
    o, outcome = await send_outreach(db=db, outreach_id=outreach_id)
    if o is None:
        raise HTTPException(status_code=404, detail="Outreach not found")
    if outcome == "not_approved":
        raise HTTPException(status_code=409, detail="Outreach must be approved before sending")
    if outcome == "rate_limited":
        raise HTTPException(status_code=429, detail="Daily send limit exceeded")
    if outcome == "send_not_configured":
        raise HTTPException(status_code=501, detail="Email sending not configured (SendGrid/Gmail API required)")
    if outcome != "sent":
        raise HTTPException(status_code=500, detail="Failed to send")
    return OutreachActionResponse(id=o.id, status=o.status, detail="sent")

