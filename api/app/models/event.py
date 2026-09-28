from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._common import created_at_column, id_column


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_ws_created", "workspace_id", "created_at"),)

    id: Mapped[str] = id_column()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String(16))  # chat | doc | login | key | settings
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str | None] = mapped_column(String(8), nullable=True)  # ok | err | accent
    tag: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
