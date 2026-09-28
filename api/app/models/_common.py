import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import utcnow


def new_id() -> str:
    return uuid.uuid4().hex


def id_column() -> Mapped[str]:
    return mapped_column(String(32), primary_key=True, default=new_id)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime, default=utcnow, nullable=False)
