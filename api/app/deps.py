"""Shared FastAPI dependencies."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models import Session, User
from app.security.sessions import load_session

Db = Annotated[DbSession, Depends(get_db)]


@dataclass
class Auth:
    user: User
    session: Session

    @property
    def workspace_id(self) -> str:
        return self.user.workspace_id


def get_auth(request: Request, db: Db) -> Auth:
    loaded = load_session(db, request)
    if loaded is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    sess, user = loaded
    return Auth(user=user, session=sess)


CurrentAuth = Annotated[Auth, Depends(get_auth)]
