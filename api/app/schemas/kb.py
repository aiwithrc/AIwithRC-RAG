from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class KbOut(BaseModel):
    id: str
    name: str
    description: str
    runtime: Literal["local", "cloud"]
    default_model: str
    default_connection_id: str | None
    doc_count: int
    indexed_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime


def _name(v: str | None) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split())
    if not v:
        raise ValueError("Give the knowledge base a name.")
    return v


class KbCreate(BaseModel):
    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=2000)
    runtime: Literal["local", "cloud"] = "local"

    _n = field_validator("name")(_name)


class KbPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    runtime: Literal["local", "cloud"] | None = None
    default_model: str | None = Field(default=None, max_length=200)
    default_connection_id: str | None = None

    _n = field_validator("name")(_name)


class DocumentOut(BaseModel):
    id: str
    kb_id: str
    filename: str
    type: str  # PDF, DOCX, …
    size_bytes: int
    size: str  # "1.2 MB"
    status: Literal["queued", "parsing", "chunking", "embedding", "indexed", "failed"]
    progress: int
    error: str | None
    chunk_count: int
    created_at: datetime


class Rejected(BaseModel):
    filename: str
    reason: str


class UploadResult(BaseModel):
    documents: list[DocumentOut]
    rejected: list[Rejected]
