from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WorkspaceSettings(Base):
    __tablename__ = "settings"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    chunk_size: Mapped[int] = mapped_column(Integer, default=800)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=120)
    top_k: Mapped[int] = mapped_column(Integer, default=5)
    hybrid: Mapped[bool] = mapped_column(Boolean, default=True)
    rerank: Mapped[bool] = mapped_column(Boolean, default=True)
    keep_local: Mapped[bool] = mapped_column(Boolean, default=True)
    ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding_provider: Mapped[str] = mapped_column(String(32), default="fastembed")
    embedding_model: Mapped[str] = mapped_column(String(200), default="BAAI/bge-small-en-v1.5")
    # Addition to the spec: workspace instructions appended to the built-in answering rules
    # (edited on the Prompt screen; read on every question, so no restart is needed).
    custom_instructions: Mapped[str] = mapped_column(Text, default="", server_default="")
