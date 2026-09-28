"""SQLAlchemy models. Importing this package registers every table on `Base.metadata`."""

from app.models.auth import Session, User, Workspace
from app.models.chat import Chat, Message, Share
from app.models.connection import ProviderConnection
from app.models.event import Event
from app.models.job import Job
from app.models.kb import Chunk, Document, KnowledgeBase
from app.models.settings import WorkspaceSettings

__all__ = [
    "Chat",
    "Chunk",
    "Document",
    "Event",
    "Job",
    "KnowledgeBase",
    "Message",
    "ProviderConnection",
    "Session",
    "Share",
    "User",
    "Workspace",
    "WorkspaceSettings",
]
