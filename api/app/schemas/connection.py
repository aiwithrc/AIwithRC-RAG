from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConnectionIn(BaseModel):
    api_base: str = Field(max_length=512)
    api_key: str = Field(default="", max_length=4096)


class ConnectionPatch(BaseModel):
    selected_model: str = Field(min_length=1, max_length=200)


class ConnectionOut(BaseModel):
    id: str
    name: str
    api_base: str
    masked_key: str
    kind: Literal["openai_compat", "anthropic"]
    runtime: Literal["local", "cloud"]
    models: list[str]
    chat_models: list[str]
    selected_model: str  # "auto" or a model id
    resolved_model: str | None  # what "auto" currently picks
    created_at: datetime


class ConnectionTestOut(BaseModel):
    name: str
    runtime: Literal["local", "cloud"]
    models: list[str]
