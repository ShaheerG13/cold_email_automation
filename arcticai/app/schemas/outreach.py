from __future__ import annotations

from pydantic import BaseModel, Field


class OutreachCreateRequest(BaseModel):
    user_id: int
    company_name: str
    company_website: str | None = None
    to_email: str
    subject: str
    body: str


class OutreachResponse(BaseModel):
    id: int
    user_id: int
    company_id: int
    email: str
    message_subject: str
    message_body: str
    status: str


class OutreachActionResponse(BaseModel):
    id: int
    status: str
    detail: str | None = None


class OutreachListResponse(BaseModel):
    items: list[OutreachResponse] = Field(default_factory=list)

