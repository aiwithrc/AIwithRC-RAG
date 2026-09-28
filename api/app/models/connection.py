from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._common import created_at_column, id_column


class ProviderConnection(Base):
    __tablename__ = "provider_connections"

    id: Mapped[str] = id_column()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    api_base: Mapped[str] = mapped_column(String(512))
    api_key_enc: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="openai_compat")  # openai_compat | anthropic
    models_json: Mapped[str] = mapped_column(Text, default="[]")
    selected_model: Mapped[str] = mapped_column(String(200), default="auto")
    created_at: Mapped[datetime] = created_at_column()
