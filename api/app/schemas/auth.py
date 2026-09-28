from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security.passwords import MIN_PASSWORD_LENGTH


def _norm_email(v: str) -> str:
    v = v.strip().lower()
    if "@" not in v or v.startswith("@") or v.endswith("@") or " " in v or len(v) > 320:
        raise ValueError("Enter a valid email address.")
    return v


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str
    password: str = Field(max_length=512)

    _email = field_validator("email")(_norm_email)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Enter your name.")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password needs at least {MIN_PASSWORD_LENGTH} characters.")
        return v


class LoginIn(BaseModel):
    email: str
    password: str = Field(max_length=512)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    role: str
    theme: str
    default_kb_id: str | None
    workspace_id: str


class MePatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    email: str | None = None
    theme: Literal["light", "dark"] | None = None
    default_kb_id: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        return None if v is None else _norm_email(v)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Name can't be empty.")
        return v


class PasswordChangeIn(BaseModel):
    current: str = Field(max_length=512)
    new: str = Field(max_length=512)

    @field_validator("new")
    @classmethod
    def _new(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"New password needs at least {MIN_PASSWORD_LENGTH} characters.")
        return v


class SessionOut(BaseModel):
    id: str
    device: str
    ip: str
    created_at: datetime
    last_seen_at: datetime
    current: bool


class AuthConfigOut(BaseModel):
    signup_open: bool
    has_users: bool
    public_host: str
