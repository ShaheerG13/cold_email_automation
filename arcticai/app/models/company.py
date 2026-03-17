from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from arcticai.app.models.base import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    website: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    field: Mapped[str | None] = mapped_column(String(200), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)

