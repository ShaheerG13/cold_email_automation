from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    location: str = Field(..., examples=["Leesburg, VA"])
    field: str = Field(..., examples=["cybersecurity"])
    experience: str = Field(..., examples=["Built vulnerability scanner using Flask and ML"])
    target_roles: list[str] = Field(default_factory=list, examples=[["intern", "junior"]])


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

