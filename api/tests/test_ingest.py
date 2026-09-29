from sqlalchemy import func, select

from app.db import SessionLocal
from app.jobs import queue
from app.models import Chunk, Document, Event, Job
from app.rag import store
from tests.conftest import PASSWORD, make_client
from tests.fixtures import FakeEmbedder, make_blank_pdf, make_docx, make_pdf, make_xlsx

MSA = make_pdf([
    "Master Services Agreement between Acme Corp and Vendor Ltd.\n\n5.2 Payment\nClient shall pay invoices within forty-five days.",
    "11.2 Termination for Convenience\nEither party may terminate this Agreement upon sixty (60) days prior written notice.",
])


def kb_id(owner) -> str:
    return owner["default_kb_id"]


def upload(client, kb: str, *files: tuple[str, bytes, str]):
    return client.post(f"/api/kbs/{kb}/documents", files=[("files", f) for f in files])


def docs(client, kb):
    return {d["filename"]: d for d in client.get(f"/api/kbs/{kb}/documents").json()}


# ---- knowledge bases ----

def test_kb_crud(client, owner):
    kbs = client.get("/api/kbs").json()
    assert [k["name"] for k in kbs] == ["My documents"]

    r = client.post("/api/kbs", json={"name": "  HR   policies ", "runtime": "cloud"})
    assert r.status_code == 201
    kb = r.json()
    assert kb["name"] == "HR policies" and kb["runtime"] == "cloud" and kb["doc_count"] == 0
    assert client.post("/api/kbs", json={"name": "   "}).status_code == 422

    r = client.patch(f"/api/kbs/{kb['id']}", json={"name": "People", "description": "Handbook", "runtime": "local"})
    assert r.json()["name"] == "People" and r.json()["runtime"] == "local"

    assert client.get(f"/api/kbs/{kb['id']}").status_code == 200
    assert client.delete(f"/api/kbs/{kb['id']}").status_code == 204
    assert client.get(f"/api/kbs/{kb['id']}").status_code == 404
    titles = [e.title for e in SessionLocal().scalars(select(Event).where(Event.category == "doc"))]
    assert titles == ["Created knowledge base HR policies", "Updated knowledge base People", "Deleted knowledge base People"]


# ---- upload validation ----

def test_upload_rejects_bad_files(client, owner):
    kb = kb_id(owner)
    r = upload(
        client, kb,
        ("virus.exe", b"MZ", "application/octet-stream"),
        ("fake.pdf", b"not really a pdf", "application/pdf"),
        ("empty.txt", b"", "text/plain"),
        ("renamed.xlsx", make_docx([("Normal", "hello")]), "application/octet-stream"),
        ("ok.txt", b"Hello world. This is fine.", "text/plain"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert [d["filename"] for d in body["documents"]] == ["ok.txt"]
    reasons = {x["filename"]: x["reason"] for x in body["rejected"]}
    assert "Unsupported file type" in reasons["virus.exe"]
    assert reasons["fake.pdf"] == "This doesn't look like a real PDF file."
    assert reasons["empty.txt"] == "The file is empty."
    assert reasons["renamed.xlsx"] == "This doesn't look like a real XLSX file."


def test_upload_size_limit(client, owner, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    r = upload(client, kb_id(owner), ("big.txt", b"a " * 600_000, "text/plain"))
    assert r.json()["rejected"][0]["reason"] == "Larger than 1 MB."


def test_duplicate_upload_rejected(client, owner):
    kb = kb_id(owner)
    assert upload(client, kb, ("a.txt", b"Same content.", "text/plain")).json()["documents"]
    r = upload(client, kb, ("b.txt", b"Same content.", "text/plain")).json()
    assert r["rejected"][0]["reason"] == "Already in this knowledge base as a.txt."


def test_path_traversal_filename_is_sanitised(client, owner):
    r = upload(client, kb_id(owner), ("../../etc/passwd.txt", b"root:x:0:0", "text/plain")).json()
    assert r["documents"][0]["filename"] == "passwd.txt"


# ---- ingest pipeline ----

def test_ingest_all_six_types(client, owner):
    kb = kb_id(owner)
    r = upload(
        client, kb,
        ("Acme_MSA.pdf", MSA, "application/pdf"),
        ("Amendment.docx", make_docx([("Heading 1", "Notice"), ("Normal", "The notice period is ninety days.")]), "x"),
        ("Rates.xlsx", make_xlsx({"Rates": [["Role", "Rate"], ["Engineer", 150]]}), "x"),
        ("people.csv", b"name,team\nAda,Research\n", "text/csv"),
        ("Runbook.md", b"# Rollback\n\nRedeploy the previous tag.", "text/markdown"),
        ("notes.txt", b"Plain notes about the vendor.", "text/plain"),
    )
    assert len(r.json()["documents"]) == 6
    assert all(d["status"] == "queued" for d in docs(client, kb).values())

    assert queue.process_all() == 6
    listed = docs(client, kb)
    assert {d["status"] for d in listed.values()} == {"indexed"}, listed
    assert all(d["progress"] == 100 and d["chunk_count"] >= 1 for d in listed.values())
    assert listed["Acme_MSA.pdf"]["type"] == "PDF" and listed["Amendment.docx"]["type"] == "DOCX"

    with SessionLocal() as db:
        term = db.scalar(select(Chunk).where(Chunk.text.contains("sixty")))
        assert term.page == 2 and term.section == "§11.2 Termination for Convenience"
        pay = db.scalar(select(Chunk).where(Chunk.text.contains("forty-five")))
        assert pay.page == 1 and pay.section == "§5.2 Payment"  # heading found mid-page
        assert db.scalar(select(func.count()).select_from(Chunk)) == store.collection(kb).count()
        # Keyword search finds it (stemming: "terminating" ~ "terminate").
        hits = store.fts_search(db, kb, "When can a party be terminating the agreement?")
        assert hits and hits[0][0] == term.id

    # Vector search with the same embedder finds it too.
    q = FakeEmbedder().embed_query("Either party may terminate this Agreement upon sixty (60) days prior written notice")
    res = store.collection(kb).query(query_embeddings=[q], n_results=1)
    assert res["ids"][0][0] == term.id

    kbs = {k["id"]: k for k in client.get("/api/kbs").json()}
    assert kbs[kb]["doc_count"] == 6 and kbs[kb]["indexed_count"] == 6

    ev = SessionLocal().scalars(select(Event).where(Event.title == "Uploaded Acme_MSA.pdf")).one()
    assert ev.tag == "Indexed" and ev.tone == "ok" and ev.detail.endswith("chunks")


def test_scanned_pdf_fails_then_retry_and_delete(client, owner):
    kb = kb_id(owner)
    doc = upload(client, kb, ("scan.pdf", make_blank_pdf(), "application/pdf")).json()["documents"][0]
    queue.process_all()
    d = docs(client, kb)["scan.pdf"]
    assert d["status"] == "failed"
    assert d["error"] == "No text layer found. Turn on OCR in Settings."
    with SessionLocal() as db:
        titles = [e.title for e in db.scalars(select(Event).where(Event.ref_id == doc["id"]))]
        assert "scan.pdf failed to index" in titles
        up = db.scalars(select(Event).where(Event.title == "Uploaded scan.pdf")).one()
        assert up.tag == "Failed"

    assert client.post(f"/api/documents/{doc['id']}/retry").json()["status"] == "queued"
    queue.process_all()
    assert docs(client, kb)["scan.pdf"]["status"] == "failed"

    ok = upload(client, kb, ("ok.txt", b"Indexed text here.", "text/plain")).json()["documents"][0]
    assert client.post(f"/api/documents/{ok['id']}/retry").status_code == 409  # only failed docs

    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert "scan.pdf" not in docs(client, kb)


def test_delete_document_removes_chunks_vectors_fts_and_file(client, owner):
    kb = kb_id(owner)
    doc = upload(client, kb, ("Acme_MSA.pdf", MSA, "application/pdf")).json()["documents"][0]
    queue.process_all()
    from app.services.files import upload_path

    with SessionLocal() as db:
        sha = db.get(Document, doc["id"]).sha256
    assert upload_path(kb, sha).exists()
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Chunk)) == 0
        assert store.fts_search(db, kb, "terminate") == []
    assert store.collection(kb).count() == 0
    assert not upload_path(kb, sha).exists()


def test_document_file_download(client, owner):
    kb = kb_id(owner)
    doc = upload(client, kb, ("page.md", b"# Hi\n<script>alert(1)</script>", "text/markdown")).json()["documents"][0]
    r = client.get(f"/api/documents/{doc['id']}/file")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "inline" in r.headers["content-disposition"]


def test_restart_requeues_interrupted_jobs(client, owner):
    kb = kb_id(owner)
    doc = upload(client, kb, ("a.txt", b"Some words.", "text/plain")).json()["documents"][0]
    job = queue.claim_next()  # simulate a crash mid-job
    assert job is not None
    with SessionLocal() as db:
        db.get(Document, doc["id"]).status = "embedding"
        db.commit()
    assert queue.requeue_stale() == 1
    assert docs(client, kb)["a.txt"]["status"] == "queued"
    assert queue.process_all() == 1
    assert docs(client, kb)["a.txt"]["status"] == "indexed"
    with SessionLocal() as db:
        assert db.scalar(select(Job).where(Job.id == job.id)).status == "done"


def test_other_users_cannot_touch_kb(app, client, owner, monkeypatch):
    """KBs are workspace-scoped; an unauthenticated client gets 401, unknown ids 404."""
    kb = kb_id(owner)
    with make_client(app) as anon:
        assert anon.get(f"/api/kbs/{kb}/documents").status_code == 401
    assert client.get("/api/kbs/not-a-kb/documents").status_code == 404
    assert client.post("/api/documents/nope/retry").status_code == 404
    _ = PASSWORD
