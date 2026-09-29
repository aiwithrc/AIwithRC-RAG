"""Workspace settings. Phase 3.5: the answering prompt. Retrieval/chunking controls join in phase 5."""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.deps import CurrentAuth, Db
from app.models import WorkspaceSettings
from app.rag.answer import MAX_INSTRUCTIONS, SYSTEM
from app.security.sessions import client_ip
from app.services import events

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsOut(BaseModel):
    chunk_size: int
    chunk_overlap: int
    top_k: int
    hybrid: bool
    rerank: bool
    keep_local: bool
    ocr: bool
    embedding_provider: str
    embedding_model: str
    custom_instructions: str
    built_in_prompt: str  # read-only: the rules every answer follows
    max_instructions: int
    can_edit: bool


class SettingsPatch(BaseModel):
    custom_instructions: str | None = Field(default=None, max_length=MAX_INSTRUCTIONS)


def _get(db: Db, workspace_id: str) -> WorkspaceSettings:
    ws = db.get(WorkspaceSettings, workspace_id)
    if ws is None:  # older workspaces
        ws = WorkspaceSettings(workspace_id=workspace_id)
        db.add(ws)
        db.flush()
    return ws


def _out(ws: WorkspaceSettings, can_edit: bool) -> SettingsOut:
    return SettingsOut(
        chunk_size=ws.chunk_size, chunk_overlap=ws.chunk_overlap, top_k=ws.top_k, hybrid=ws.hybrid,
        rerank=ws.rerank, keep_local=ws.keep_local, ocr=ws.ocr, embedding_provider=ws.embedding_provider,
        embedding_model=ws.embedding_model, custom_instructions=ws.custom_instructions or "",
        built_in_prompt=SYSTEM, max_instructions=MAX_INSTRUCTIONS, can_edit=can_edit,
    )


@router.get("", response_model=SettingsOut)
def get_settings(auth: CurrentAuth, db: Db) -> SettingsOut:
    ws = _get(db, auth.workspace_id)
    db.commit()
    return _out(ws, auth.user.role == "owner")


@router.patch("", response_model=SettingsOut)
def patch_settings(body: SettingsPatch, auth: CurrentAuth, request: Request, db: Db) -> SettingsOut:
    if auth.user.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the workspace owner can change settings.")
    ws = _get(db, auth.workspace_id)
    if body.custom_instructions is not None:
        new = body.custom_instructions.strip()
        old = ws.custom_instructions or ""
        if new != old:
            ws.custom_instructions = new
            words = len(new.split())
            events.record(
                db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="settings",
                title="Prompt instructions cleared" if not new else "Prompt instructions updated",
                detail=f"{len(old.split())} → {words} words", ip=client_ip(request),
            )
    db.commit()
    return _out(ws, True)
