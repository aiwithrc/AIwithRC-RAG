import hashlib
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.config import get_settings
from app.deps import CurrentAuth, Db
from app.jobs import queue
from app.models import Document
from app.rag import store
from app.rag.parse import file_type, sniff_ok
from app.routers.kbs import get_kb_or_404
from app.schemas.kb import DocumentOut, Rejected, UploadResult
from app.security.sessions import client_ip
from app.services import events
from app.services.files import human_size, upload_path

router = APIRouter(tags=["documents"])

MAX_FILES_PER_UPLOAD = 20
_COPY_CHUNK = 1024 * 1024


def to_out(d: Document) -> DocumentOut:
    ft = file_type(d.filename)
    return DocumentOut(
        id=d.id, kb_id=d.kb_id, filename=d.filename, type=ft.label if ft else "FILE", size_bytes=d.size_bytes,
        size=human_size(d.size_bytes), status=d.status, progress=d.progress, error=d.error,
        chunk_count=d.chunk_count, created_at=d.created_at,
    )


def safe_filename(name: str | None) -> str:
    name = unicodedata.normalize("NFC", os.path.basename((name or "").replace("\\", "/")))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().strip(".")
    return name[:255] or "untitled"


def _spool(upload: UploadFile, limit: int, tmp_dir: Path) -> tuple[Path, str, int, bytes] | None:
    """Copy an upload to a temp file while hashing. None if it exceeds `limit` bytes."""
    h = hashlib.sha256()
    size = 0
    head = b""
    fd, tmp = tempfile.mkstemp(dir=tmp_dir)
    path = Path(tmp)
    with os.fdopen(fd, "wb") as out:
        upload.file.seek(0)
        while chunk := upload.file.read(_COPY_CHUNK):
            size += len(chunk)
            if size > limit:
                out.close()
                path.unlink(missing_ok=True)
                return None
            if len(head) < 8192:
                head += chunk[: 8192 - len(head)]
            h.update(chunk)
            out.write(chunk)
    return path, h.hexdigest(), size, head


def _store_uploads(db: Db, auth: CurrentAuth, kb_id: str, uploads: list[UploadFile], ip: str) -> UploadResult:
    settings = get_settings()
    kb = get_kb_or_404(db, auth.workspace_id, kb_id)
    tmp_dir = settings.data_dir / "uploads" / ".incoming"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    accepted: list[Document] = []
    rejected: list[Rejected] = []
    seen: set[str] = set()

    for up in uploads:
        name = safe_filename(up.filename)
        ft = file_type(name)
        if ft is None:
            rejected.append(Rejected(filename=name, reason="Unsupported file type. Use PDF, DOCX, MD, TXT, CSV or XLSX."))
            continue
        spooled = _spool(up, settings.max_upload_bytes, tmp_dir)
        if spooled is None:
            rejected.append(Rejected(filename=name, reason=f"Larger than {settings.max_upload_mb} MB."))
            continue
        tmp, sha, size, head = spooled
        try:
            if size == 0:
                rejected.append(Rejected(filename=name, reason="The file is empty."))
                continue
            if not sniff_ok(ft, head, tmp):
                rejected.append(Rejected(filename=name, reason=f"This doesn't look like a real {ft.label} file."))
                continue
            dup = db.scalar(select(Document).where(Document.kb_id == kb.id, Document.sha256 == sha))
            if dup is not None or sha in seen:
                where = f" as {dup.filename}" if dup is not None and dup.filename != name else ""
                rejected.append(Rejected(filename=name, reason=f"Already in this knowledge base{where}."))
                continue
            dest = upload_path(kb.id, sha)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, dest)
            seen.add(sha)
        finally:
            tmp.unlink(missing_ok=True)

        doc = Document(kb_id=kb.id, filename=name, mime=ft.mime, size_bytes=size, sha256=sha, status="queued")
        db.add(doc)
        db.flush()
        queue.enqueue(db, "ingest", {"document_id": doc.id})
        events.record(
            db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="doc", title=f"Uploaded {name}",
            detail=f"{kb.name} · {human_size(size)}", tag="Indexing", tone="accent",
            ref_type="document", ref_id=doc.id, ip=ip,
        )
        accepted.append(doc)

    db.commit()
    if accepted:
        queue.notify()
    return UploadResult(documents=[to_out(d) for d in accepted], rejected=rejected)


@router.post("/kbs/{kb_id}/documents", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_documents(kb_id: str, request: Request, auth: CurrentAuth, db: Db) -> UploadResult:
    settings = get_settings()
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.max_upload_bytes * MAX_FILES_PER_UPLOAD + 1_000_000:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Upload is too large.")
    form = await request.form(max_files=MAX_FILES_PER_UPLOAD, max_fields=10)
    try:
        uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
        if not uploads:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose at least one file to upload.")
        return await run_in_threadpool(_store_uploads, db, auth, kb_id, uploads, client_ip(request))
    finally:
        await form.close()


@router.get("/kbs/{kb_id}/documents", response_model=list[DocumentOut])
def list_documents(kb_id: str, auth: CurrentAuth, db: Db) -> list[DocumentOut]:
    get_kb_or_404(db, auth.workspace_id, kb_id)
    docs = db.scalars(select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at.desc()))
    return [to_out(d) for d in docs]


def _doc_or_404(db: Db, auth: CurrentAuth, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    get_kb_or_404(db, auth.workspace_id, doc.kb_id)
    return doc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, auth: CurrentAuth, request: Request, db: Db) -> Response:
    doc = _doc_or_404(db, auth, document_id)
    kb = get_kb_or_404(db, auth.workspace_id, doc.kb_id)
    kb_id, sha, name = doc.kb_id, doc.sha256, doc.filename
    store.fts_delete_document(db, doc.id)
    db.delete(doc)  # cascades to chunks
    events.record(
        db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="doc", title=f"Deleted {name}",
        detail=kb.name, ref_type="kb", ref_id=kb_id, ip=client_ip(request),
    )
    db.commit()
    store.delete_document_vectors(kb_id, document_id)
    upload_path(kb_id, sha).unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/retry", response_model=DocumentOut)
def retry_document(document_id: str, auth: CurrentAuth, db: Db) -> DocumentOut:
    doc = _doc_or_404(db, auth, document_id)
    if doc.status != "failed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed documents can be retried.")
    doc.status, doc.progress, doc.error = "queued", 0, None
    queue.enqueue(db, "ingest", {"document_id": doc.id})
    db.commit()
    queue.notify()
    return to_out(doc)


@router.get("/documents/{document_id}/file")
def document_file(document_id: str, auth: CurrentAuth, db: Db) -> FileResponse:
    doc = _doc_or_404(db, auth, document_id)
    path = upload_path(doc.kb_id, doc.sha256)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The file is missing from the server.")
    ft = file_type(doc.filename)
    # Text formats are served as plain text so the browser never renders uploaded HTML/JS.
    is_text = ft is not None and ft.mime.startswith("text/")
    media = "text/plain; charset=utf-8" if is_text else (doc.mime or "application/octet-stream")
    inline = ft is not None and ft.ext in ("pdf", "txt", "md", "markdown", "csv")
    return FileResponse(
        path, media_type=media, filename=doc.filename, content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )
