from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arcticai.app.models.company import Company
from arcticai.app.models.outreach import Outreach
from arcticai.app.services.email_sender import SendNotConfigured, send_email
from arcticai.app.utils.rate_limit import RateLimitExceeded, enforce_daily_limit
from arcticai.app.utils.debug_log import dlog


async def create_outreach(
    *,
    db: AsyncSession,
    user_id: int,
    company_name: str,
    company_website: str | None,
    to_email: str,
    subject: str,
    body: str,
) -> Outreach:
    # region agent log
    dlog(
        location="arcticai/app/services/outreach_service.py:create_outreach",
        message="create_outreach_start",
        data={"user_id": user_id, "has_company_website": bool(company_website)},
        run_id="pre-fix",
        hypothesis_id="H4",
    )
    # endregion
    company = Company(name=company_name, website=company_website)
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
    # region agent log
    dlog(
        location="arcticai/app/services/outreach_service.py:create_outreach",
        message="create_outreach_done",
        data={"outreach_id": outreach.id, "company_id": outreach.company_id, "status": outreach.status},
        run_id="pre-fix",
        hypothesis_id="H4",
    )
    # endregion
    return outreach


async def list_outreach(*, db: AsyncSession, user_id: int) -> list[Outreach]:
    res = await db.execute(select(Outreach).where(Outreach.user_id == user_id).order_by(Outreach.id.desc()))
    return list(res.scalars().all())


async def set_status(*, db: AsyncSession, outreach_id: int, status: str) -> Outreach | None:
    outreach = await db.get(Outreach, outreach_id)
    if outreach is None:
        return None
    outreach.status = status
    await db.commit()
    await db.refresh(outreach)
    return outreach


async def send_outreach(*, db: AsyncSession, outreach_id: int) -> tuple[Outreach | None, str]:
    outreach = await db.get(Outreach, outreach_id)
    if outreach is None:
        # region agent log
        dlog(
            location="arcticai/app/services/outreach_service.py:send_outreach",
            message="send_outreach_not_found",
            data={"outreach_id": outreach_id},
            run_id="pre-fix",
            hypothesis_id="H4",
        )
        # endregion
        return None, "not_found"

    if outreach.status != "approved":
        # region agent log
        dlog(
            location="arcticai/app/services/outreach_service.py:send_outreach",
            message="send_outreach_not_approved",
            data={"outreach_id": outreach_id, "status": outreach.status},
            run_id="pre-fix",
            hypothesis_id="H4",
        )
        # endregion
        return outreach, "not_approved"

    try:
        await enforce_daily_limit(key=f"user:{outreach.user_id}:send", max_per_day=5)
    except RateLimitExceeded:
        # region agent log
        dlog(
            location="arcticai/app/services/outreach_service.py:send_outreach",
            message="send_outreach_rate_limited",
            data={"outreach_id": outreach_id, "user_id": outreach.user_id},
            run_id="pre-fix",
            hypothesis_id="H3",
        )
        # endregion
        return outreach, "rate_limited"

    try:
        await send_email(to=outreach.email, subject=outreach.message_subject, body=outreach.message_body)
    except SendNotConfigured:
        # region agent log
        dlog(
            location="arcticai/app/services/outreach_service.py:send_outreach",
            message="send_outreach_send_not_configured",
            data={"outreach_id": outreach_id},
            run_id="pre-fix",
            hypothesis_id="H5",
        )
        # endregion
        return outreach, "send_not_configured"

    outreach.status = "sent"
    await db.commit()
    await db.refresh(outreach)
    # region agent log
    dlog(
        location="arcticai/app/services/outreach_service.py:send_outreach",
        message="send_outreach_sent",
        data={"outreach_id": outreach_id},
        run_id="pre-fix",
        hypothesis_id="H4",
    )
    # endregion
    return outreach, "sent"

