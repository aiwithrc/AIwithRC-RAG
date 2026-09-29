from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatCreate(BaseModel):
    kb_id: str


class ChatOut(BaseModel):
    id: str
    title: str
    kb_id: str | None
    kb_name: str | None
    message_count: int
    created_at: datetime
    updated_at: datetime


class CitationOut(BaseModel):
    n: int
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    section: str | None
    location: str
    score: float
    chunk: int
    total: int
    before: str
    hit: str
    after: str


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    model: str | None
    connection_id: str | None
    connection_name: str | None
    runtime: Literal["local", "cloud"] | None
    confidence: Literal["high", "low"] | None
    citations: list[CitationOut]
    followups: list[str]
    error: str | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tokens_estimated: bool = False
    created_at: datetime


class ChatDetail(BaseModel):
    chat: ChatOut
    messages: list[MessageOut]


class AskIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    connection_id: str | None = None
    model: str | None = Field(default=None, max_length=200)


class RegenerateIn(BaseModel):
    connection_id: str | None = None
    model: str | None = Field(default=None, max_length=200)
