from __future__ import annotations

from typing import Literal

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arcticai.app.models.base import Base

OutreachStatus = Literal["pending", "approved", "sent", "rejected", "failed"]


class Outreach(Base):
    __tablename__ = "outreach"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)

    email: Mapped[str] = mapped_column(String(320))
    message_subject: Mapped[str] = mapped_column(String(300))
    message_body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    user: Mapped["User"] = relationship(backref="outreach")
    company: Mapped["Company"] = relationship(backref="outreach")

