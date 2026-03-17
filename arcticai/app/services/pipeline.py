from __future__ import annotations

from arcticai.app.schemas.pipeline import (
    CompanyCandidate,
    ContactCandidate,
    EmailDraft,
    PipelineResultItem,
    PipelineRunRequest,
    PipelineRunResponse,
)
from arcticai.app.services.ai_generator import generate_email_draft
from arcticai.app.services.company_finder import find_companies
from arcticai.app.services.enrichment import enrich_company
from arcticai.app.services.email_finder import find_relevant_emails
from arcticai.app.utils.debug_log import dlog


async def run_pipeline(request: PipelineRunRequest) -> PipelineRunResponse:
    # region agent log
    dlog(
        location="arcticai/app/services/pipeline.py:run_pipeline",
        message="pipeline_start",
        data={"location": request.location, "field": request.field, "target_roles_count": len(request.target_roles)},
        run_id="pre-fix",
        hypothesis_id="H1",
    )
    # endregion
    companies = await find_companies(location=request.location, field=request.field)
    # region agent log
    dlog(
        location="arcticai/app/services/pipeline.py:run_pipeline",
        message="companies_found",
        data={"count": len(companies), "has_websites": sum(1 for c in companies if c.website)},
        run_id="pre-fix",
        hypothesis_id="H1",
    )
    # endregion

    items: list[PipelineResultItem] = []
    for c in companies:
        enriched: CompanyCandidate = await enrich_company(c)
        contacts: list[ContactCandidate] = await find_relevant_emails(enriched)

        draft: EmailDraft | None = None
        if contacts:
            draft = await generate_email_draft(
                user_experience=request.experience,
                target_field=request.field,
                company_name=enriched.name,
                company_about=enriched.about or "",
            )

        items.append(PipelineResultItem(company=enriched, contacts=contacts, draft=draft))

    # region agent log
    dlog(
        location="arcticai/app/services/pipeline.py:run_pipeline",
        message="pipeline_done",
        data={
            "items": len(items),
            "with_contacts": sum(1 for i in items if i.contacts),
            "with_drafts": sum(1 for i in items if i.draft),
        },
        run_id="pre-fix",
        hypothesis_id="H1",
    )
    # endregion
    return PipelineRunResponse(items=items)

