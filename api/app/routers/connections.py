"""Model provider connections: an API Base + key, validated by listing the provider's models."""

import json

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.deps import CurrentAuth, Db
from app.models import ProviderConnection
from app.providers.auto import resolve_model
from app.providers.base import ProviderError, display_name, is_chat_model, kind_for, normalize_base, runtime_for
from app.providers.catalog import list_models
from app.schemas.connection import ConnectionIn, ConnectionOut, ConnectionPatch, ConnectionTestOut
from app.security.crypto import decrypt, encrypt, mask_key
from app.security.sessions import client_ip
from app.services import events

router = APIRouter(prefix="/connections", tags=["connections"])


def to_out(c: ProviderConnection) -> ConnectionOut:
    models: list[str] = json.loads(c.models_json or "[]")
    try:
        masked = mask_key(decrypt(c.api_key_enc)) if c.api_key_enc else "No key"
    except ValueError:
        masked = "Key unreadable (APP_SECRET changed)"
    return ConnectionOut(
        id=c.id, name=c.name, api_base=c.api_base, masked_key=masked, kind=c.kind,
        runtime=runtime_for(c.api_base), models=models, chat_models=[m for m in models if is_chat_model(m)],
        selected_model=c.selected_model, resolved_model=resolve_model(c.selected_model, models),
        created_at=c.created_at,
    )


def _validate(body: ConnectionIn) -> tuple[str, str]:
    try:
        base = normalize_base(body.api_base)
    except ProviderError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    key = body.api_key.strip()
    if not key and runtime_for(base) == "cloud":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter an API key.")
    return base, key


async def _fetch_models(base: str, key: str) -> list[str]:
    try:
        return await run_in_threadpool(list_models, base, key)
    except ProviderError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.get("", response_model=list[ConnectionOut])
def list_connections(auth: CurrentAuth, db: Db) -> list[ConnectionOut]:
    rows = db.scalars(
        select(ProviderConnection)
        .where(ProviderConnection.workspace_id == auth.workspace_id)
        .order_by(ProviderConnection.created_at)
    )
    return [to_out(c) for c in rows]


@router.post("/test", response_model=ConnectionTestOut)
async def test_connection(body: ConnectionIn, auth: CurrentAuth) -> ConnectionTestOut:
    base, key = _validate(body)
    models = await _fetch_models(base, key)
    return ConnectionTestOut(name=display_name(base), runtime=runtime_for(base), models=models)


@router.post("", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(body: ConnectionIn, auth: CurrentAuth, request: Request, db: Db) -> ConnectionOut:
    base, key = _validate(body)
    exists = db.scalar(
        select(ProviderConnection.id).where(
            ProviderConnection.workspace_id == auth.workspace_id, ProviderConnection.api_base == base
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "This API Base is already connected. Remove it first to change the key.")
    models = await _fetch_models(base, key)
    conn = ProviderConnection(
        workspace_id=auth.workspace_id, name=display_name(base), api_base=base,
        api_key_enc=encrypt(key) if key else "", kind=kind_for(base), models_json=json.dumps(models),
        selected_model="auto",
    )
    db.add(conn)
    db.flush()
    events.record(
        db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="key", title="Provider connected",
        detail=f"{conn.name} · {base} · {len(models)} models", tone="ok", tag="Connected",
        ref_type="connection", ref_id=conn.id, ip=client_ip(request),
    )
    db.commit()
    return to_out(conn)


def _get(db: Db, auth: CurrentAuth, connection_id: str) -> ProviderConnection:
    conn = db.get(ProviderConnection, connection_id)
    if conn is None or conn.workspace_id != auth.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider connection not found.")
    return conn


@router.patch("/{connection_id}", response_model=ConnectionOut)
def patch_connection(connection_id: str, body: ConnectionPatch, auth: CurrentAuth, request: Request, db: Db) -> ConnectionOut:
    conn = _get(db, auth, connection_id)
    models = json.loads(conn.models_json or "[]")
    if body.selected_model != "auto" and body.selected_model not in models:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That model isn't offered by this provider.")
    if body.selected_model != conn.selected_model:
        old = conn.selected_model
        conn.selected_model = body.selected_model
        label = lambda m: "Auto" if m == "auto" else m  # noqa: E731
        events.record(
            db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="key", title="Model changed",
            detail=f"{conn.name} · {label(old)} → {label(body.selected_model)}",
            ref_type="connection", ref_id=conn.id, ip=client_ip(request),
        )
        db.commit()
    return to_out(conn)


@router.post("/{connection_id}/refresh", response_model=ConnectionOut)
async def refresh_connection(connection_id: str, auth: CurrentAuth, db: Db) -> ConnectionOut:
    """Re-list models (e.g. after downloading a new one in LM Studio or Ollama)."""
    conn = _get(db, auth, connection_id)
    try:
        key = decrypt(conn.api_key_enc) if conn.api_key_enc else ""
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    models = await _fetch_models(conn.api_base, key)
    conn.models_json = json.dumps(models)
    if conn.selected_model != "auto" and conn.selected_model not in models:
        conn.selected_model = "auto"
    db.commit()
    return to_out(conn)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: str, auth: CurrentAuth, request: Request, db: Db) -> Response:
    conn = _get(db, auth, connection_id)
    events.record(
        db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="key", title="Provider removed",
        detail=f"{conn.name} · {conn.api_base}", tone="err", ip=client_ip(request),
    )
    db.delete(conn)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
