from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    location: str
    field: str
    experience: str
    target_roles: list[str] = Field(default_factory=list)


class CompanyCandidate(BaseModel):
    name: str
    website: str | None = None
    about: str | None = None
    keywords: list[str] = Field(default_factory=list)


class ContactCandidate(BaseModel):
    email: str
    role_guess: str | None = None
    source: Literal["api", "scrape"] = "scrape"


class EmailDraft(BaseModel):
    subject: str
    body: str
    include_unsubscribe_line: bool = True


class PipelineResultItem(BaseModel):
    company: CompanyCandidate
    contacts: list[ContactCandidate] = Field(default_factory=list)
    draft: EmailDraft | None = None


class PipelineRunResponse(BaseModel):
    items: list[PipelineResultItem]


class EmailAccountCreate(BaseModel):
    user_id: int
    label: str
    sendgrid_api_key: str
    from_email: str


class EmailAccountOut(BaseModel):
    id: int
    user_id: int
    label: str
    from_email: str


class OutreachCreateRequest(BaseModel):
    user_id: int
    company_name: str
    company_website: str | None = None
    to_email: str
    subject: str
    body: str
    from_account_id: int | None = None


class OutreachResponse(BaseModel):
    id: int
    user_id: int
    company_id: int
    email: str
    message_subject: str
    message_body: str
    status: str
    from_account_id: int | None = None


class OutreachActionResponse(BaseModel):
    id: int
    status: str
    detail: str | None = None


class OutreachListResponse(BaseModel):
    items: list[OutreachResponse] = Field(default_factory=list)


class OutreachUpdateRequest(BaseModel):
    to_email: str | None = None
    subject: str | None = None
    body: str | None = None


class CompanyCreate(BaseModel):
    name: str
    website: str | None = None
    location: str | None = None
    field: str | None = None
    about: str | None = None


class CompanyOut(BaseModel):
    id: int
    name: str
    website: str | None = None
    location: str | None = None
    field: str | None = None
    about: str | None = None

