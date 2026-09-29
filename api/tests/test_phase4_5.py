"""Sharing, suggested questions, History (events) and Settings."""

from sqlalchemy import select

from app.db import SessionLocal
from app.jobs import queue
from app.models import Document
from app.rag import answer
from tests.test_chat import ask, model, setup, sse  # noqa: F401  (fixtures)
from tests.test_ingest import MSA, upload


def _answer_id(client, chat_id: str) -> str:
    return ask(client, chat_id, "How much notice to terminate?")[-2][1]["message"]["id"]


# ---- sharing ----

def test_share_public_page_and_revoke(app, client, setup, model):
    from tests.conftest import make_client

    mid = _answer_id(client, setup["chat"]["id"])
    r = client.post(f"/api/messages/{mid}/share", json={"include_sources": True})
    assert r.status_code == 200
    share = r.json()
    assert share["url"] == f"http://localhost:8000/s/{share['token']}" and len(share["token"]) >= 12
    # Sharing again returns the same link.
    assert client.post(f"/api/messages/{mid}/share", json={"include_sources": True}).json()["id"] == share["id"]

    with make_client(app) as anon:  # logged out
        pub = anon.get(f"/api/public/shares/{share['token']}")
        assert pub.status_code == 200 and pub.headers["x-robots-tag"] == "noindex"
        body = pub.json()
        assert body["question"] == "How much notice to terminate?"
        assert "60 days" in body["answer"] and body["citations"][0]["filename"] == "Acme_MSA.pdf"
        assert set(body) == {"question", "answer", "confidence", "model", "kb_name", "answered_at", "citations",
                             "include_sources", "project_url"}  # nothing else leaks

        page = anon.get(f"/s/{share['token']}")
        assert page.status_code == 200
        assert 'content="noindex, nofollow"' in page.text
        assert 'property="og:title" content="How much notice to terminate?"' in page.text

        # Hide sources.
        client.patch(f"/api/shares/{share['id']}", json={"include_sources": False})
        assert anon.get(f"/api/public/shares/{share['token']}").json()["citations"] == []

        # Snapshot: deleting the chat doesn't change the shared page.
        client.delete(f"/api/chats/{setup['chat']['id']}")
        assert anon.get(f"/api/public/shares/{share['token']}").status_code == 200

        assert client.delete(f"/api/shares/{share['id']}").status_code == 404  # chat gone -> not yours anymore


def test_revoke_share(app, client, setup, model):
    from tests.conftest import make_client

    mid = _answer_id(client, setup["chat"]["id"])
    share = client.post(f"/api/messages/{mid}/share", json={}).json()
    assert client.delete(f"/api/shares/{share['id']}").status_code == 204
    with make_client(app) as anon:
        assert anon.get(f"/api/public/shares/{share['token']}").status_code == 404
        assert anon.get(f"/s/{share['token']}").status_code == 404
    assert client.post("/api/messages/nope/share", json={}).status_code == 404


# ---- suggested questions ----

def test_suggestions_generated_once_and_cached(client, setup, model):
    model.requests.clear()
    r = client.get(f"/api/kbs/{setup['kb']}/suggestions").json()
    assert r["filename"] == "Acme_MSA.pdf" and len(r["questions"]) == 3
    assert model.requests[0]["messages"][0]["content"].startswith(answer.STARTER_SYSTEM[:30])
    model.requests.clear()
    assert client.get(f"/api/kbs/{setup['kb']}/suggestions").json() == r
    assert model.requests == []  # cached on the document
    with SessionLocal() as db:
        assert db.scalars(select(Document)).first().suggestions_json


def test_suggestions_without_documents_or_model(client, owner):
    kb = client.post("/api/kbs", json={"name": "Empty"}).json()
    assert client.get(f"/api/kbs/{kb['id']}/suggestions").json() == {"document_id": None, "filename": None, "questions": []}
    upload(client, kb["id"], ("Acme_MSA.pdf", MSA, "application/pdf"))
    queue.process_all()
    r = client.get(f"/api/kbs/{kb['id']}/suggestions").json()  # no model connected
    assert r["filename"] == "Acme_MSA.pdf" and r["questions"] == []


# ---- History ----

def test_events_tabs_search_links_and_csv(client, setup, model):
    ask(client, setup["chat"]["id"], "How much notice to terminate?")
    page = client.get("/api/events").json()
    assert page["counts"]["all"] == sum(page["counts"][c] for c in ("chat", "doc", "login", "key", "settings"))
    titles = [e["title"] for e in page["items"]]
    assert "How much notice to terminate?" in titles and "Provider connected" in titles and "Uploaded Acme_MSA.pdf" in titles
    chat_ev = next(e for e in page["items"] if e["category"] == "chat")
    assert chat_ev["link"] == f"/c/{setup['chat']['id']}"
    doc_ev = next(e for e in page["items"] if e["title"] == "Uploaded Acme_MSA.pdf")
    assert doc_ev["link"] == f"/kbs/{setup['kb']}" and doc_ev["tag"] == "Indexed"
    signup = next(e for e in page["items"] if e["title"] == "Account created")
    assert signup["tag"] == "This device"  # the current session

    docs_only = client.get("/api/events?category=doc").json()["items"]
    assert docs_only and all(e["category"] == "doc" for e in docs_only)
    found = client.get("/api/events?q=acme_msa").json()["items"]
    assert found and all("acme_msa" in (e["title"] + e["detail"]).lower() for e in found)

    csv = client.get("/api/events.csv")
    assert csv.headers["content-type"].startswith("text/csv") and "attachment" in csv.headers["content-disposition"]
    lines = csv.text.lstrip("﻿").splitlines()
    assert lines[0] == "time_utc,category,title,detail,tag,user,ip" and len(lines) == page["counts"]["all"] + 1


# ---- Settings ----

def test_settings_toggles_and_reindex_on_chunking_change(client, setup, model):
    r = client.patch("/api/settings", json={"hybrid": False, "top_k": 3})
    assert r.status_code == 200 and r.json()["hybrid"] is False and r.json()["top_k"] == 3 and r.json()["reindexing"] == 0

    assert client.patch("/api/settings", json={"chunk_size": 200, "chunk_overlap": 120}).status_code == 422
    r = client.patch("/api/settings", json={"chunk_size": 400})
    assert r.json()["reindexing"] == 1
    assert queue.process_all() == 1
    docs = client.get(f"/api/kbs/{setup['kb']}/documents").json()
    assert docs[0]["status"] == "indexed"

    titles = [e["title"] for e in client.get("/api/events?category=settings").json()["items"]]
    assert "Hybrid search turned off" in titles and "Passages per answer changed" in titles and "Chunking changed" in titles
    chunk_ev = next(e for e in client.get("/api/events?category=settings").json()["items"] if e["title"] == "Chunking changed")
    assert chunk_ev["detail"] == "Chunk size 800 → 400 tokens · 1 document re-indexed"

    assert client.patch("/api/settings", json={"embedding_model": "not/a-model"}).status_code == 422
    s = client.get("/api/settings").json()
    assert s["embedding_dims"] == 384 and "BAAI/bge-base-en-v1.5" in s["embedding_models"]

    # Answers still work after the re-index.
    evs = ask(client, setup["chat"]["id"], "How much notice to terminate?")
    assert evs[-2][0] == "done"
