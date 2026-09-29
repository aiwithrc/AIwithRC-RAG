"""Chats and streaming answers against a fake OpenAI-compatible / Anthropic model server."""

import json

import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.jobs import queue
from app.models import Event, WorkspaceSettings
from app.providers import catalog
from app.providers import chat as chat_provider
from app.rag import answer, rerank
from tests.test_ingest import MSA, upload
from tests.test_retrieval import KeywordReranker

LOCAL = "http://host.docker.internal:1234/v1"


class FakeModel:
    """Scriptable model server. `answer` streams in small pieces; other calls get short completions."""

    def __init__(self):
        self.answer = "<think>reasoning…</think>Either party can end it with **60 days' written notice** [1]. Unrelated [7]."
        self.fail_with: int | None = None
        self.requests: list[dict] = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models"):
            ids = ["claude-sonnet-4-5"] if req.url.host == "api.anthropic.com" else ["qwen/qwen3.5-9b", "google/gemma-4-e2b"]
            return httpx.Response(200, json={"data": [{"id": m} for m in ids]})
        body = json.loads(req.content)
        self.requests.append(body)
        if self.fail_with:
            return httpx.Response(self.fail_with, json={"error": {"message": "Model is not loaded"}})
        system = body["system"] if "system" in body else body["messages"][0]["content"]
        if system.startswith(answer.REWRITE_SYSTEM[:20]):
            text = "What is the notice period to terminate the Acme agreement?"
        elif system.startswith(answer.FOLLOWUP_SYSTEM[:20]):
            text = '["Can the client terminate for breach?", "When are invoices due?", "What is the notice period?"]'
        else:
            text = self.answer
        pieces = [text[i : i + 7] for i in range(0, len(text), 7)]
        if req.url.host == "api.anthropic.com":
            lines = [f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': p}})}\n" for p in pieces]
        else:
            lines = [f"data: {json.dumps({'choices': [{'delta': {'content': p}}]})}\n" for p in pieces] + ["data: [DONE]\n"]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content="\n".join(lines).encode())


@pytest.fixture
def model(monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(catalog, "transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(chat_provider, "transport", httpx.MockTransport(fake.handler))
    rerank.set_reranker(KeywordReranker())
    yield fake
    rerank.set_reranker(None)


@pytest.fixture
def setup(client, owner, model):
    kb = owner["default_kb_id"]
    upload(client, kb, ("Acme_MSA.pdf", MSA, "application/pdf"))
    queue.process_all()
    conn = client.post("/api/connections", json={"api_base": LOCAL}).json()
    chat = client.post("/api/chats", json={"kb_id": kb}).json()
    return {"kb": kb, "conn": conn, "chat": chat}


def sse(resp: httpx.Response) -> list[tuple[str, dict]]:
    out = []
    for block in resp.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def ask(client, chat_id, content, **kw):
    r = client.post(f"/api/chats/{chat_id}/messages", json={"content": content, **kw})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return sse(r)


def test_streams_cited_answer(client, setup, model):
    evs = ask(client, setup["chat"]["id"], "How much notice to terminate?")
    kinds = [k for k, _ in evs]
    assert kinds[0] == "start" and kinds[1] == "status" and kinds[-2:] == ["done", "followups"]
    streamed = "".join(d["t"] for k, d in evs if k == "token")
    assert "reasoning" not in streamed and streamed.startswith("Either party")  # <think> hidden while streaming

    msg = evs[-2][1]["message"]
    assert evs[-1][1] == {"message_id": msg["id"], "followups": [
        "Can the client terminate for breach?", "When are invoices due?", "What is the notice period?"]}
    assert msg["content"] == "Either party can end it with **60 days' written notice** [1]. Unrelated."
    assert msg["confidence"] == "high"
    assert msg["model"] == "qwen/qwen3.5-9b" and msg["connection_name"] == "LM Studio" and msg["runtime"] == "local"
    [c] = msg["citations"]
    assert c["n"] == 1 and c["filename"] == "Acme_MSA.pdf" and c["page"] == 2
    assert c["section"] == "§11.2 Termination for Convenience"
    assert c["hit"].startswith("Either party may terminate") and 0.75 <= c["score"] <= 1
    assert msg["followups"] == []  # delivered in the next event, then saved

    # The answer prompt got numbered passages and the /no_think switch for Qwen3-family models.
    answer_req = next(r for r in model.requests if "Passages:" in r["messages"][-1]["content"] and "Question:" in r["messages"][-1]["content"])
    assert "[1] Acme_MSA.pdf" in answer_req["messages"][-1]["content"]
    assert answer_req["messages"][0]["content"].endswith("/no_think") and answer_req["stream"] is True

    detail = client.get(f"/api/chats/{setup['chat']['id']}").json()
    assert detail["messages"][1]["followups"][0] == "Can the client terminate for breach?"
    assert detail["chat"]["title"] == "How much notice to terminate?"
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert client.get("/api/chats").json()[0]["message_count"] == 2
    ev = SessionLocal().scalars(select(Event).where(Event.category == "chat")).one()
    assert ev.title == "How much notice to terminate?" and ev.detail == "My documents · 2 messages"


def test_follow_up_is_rewritten_with_history(client, setup, model):
    ask(client, setup["chat"]["id"], "How much notice to terminate the Acme agreement?")
    model.requests.clear()
    ask(client, setup["chat"]["id"], "and what about for breach?")
    rewrite_req = model.requests[0]
    assert rewrite_req["messages"][0]["content"].startswith(answer.REWRITE_SYSTEM[:20])
    assert "How much notice to terminate the Acme agreement?" in rewrite_req["messages"][-1]["content"]
    answer_req = model.requests[1]
    assert "Question: What is the notice period to terminate the Acme agreement?" in answer_req["messages"][-1]["content"]


def test_standalone_follow_up_skips_rewrite(client, setup, model):
    ask(client, setup["chat"]["id"], "How much notice to terminate the Acme agreement?")
    model.requests.clear()
    ask(client, setup["chat"]["id"], "When are invoices due under the Acme agreement?")
    assert not model.requests[0]["messages"][0]["content"].startswith(answer.REWRITE_SYSTEM[:20])
    assert answer.needs_rewrite("and for breach?") and answer.needs_rewrite("What did he study?")
    assert not answer.needs_rewrite("When are invoices due under the Acme agreement?")


def test_nothing_relevant_skips_the_model(client, setup, model):
    model.requests.clear()
    msg = ask(client, setup["chat"]["id"], "zebra migration patterns")[-1][1]["message"]  # no follow-ups event
    assert msg["content"] == answer.NOT_FOUND
    assert msg["confidence"] == "low" and len(msg["citations"]) == 1 and msg["citations"][0]["n"] == 1
    assert model.requests == []  # no LLM call


def test_empty_kb_message(client, owner, model):
    kb = client.post("/api/kbs", json={"name": "Empty"}).json()
    client.post("/api/connections", json={"api_base": LOCAL})
    chat = client.post("/api/chats", json={"kb_id": kb["id"]}).json()
    msg = ask(client, chat["id"], "anything?")[-1][1]["message"]
    assert "no indexed documents in Empty" in msg["content"] and msg["confidence"] is None


def test_model_error_is_saved_and_regenerate_recovers(client, setup, model):
    model.fail_with = 400
    evs = ask(client, setup["chat"]["id"], "How much notice to terminate?")
    kind, data = evs[-1]
    assert kind == "error" and "Model is not loaded" in data["detail"]
    failed = data["message"]
    assert failed["error"] and failed["content"] == ""

    model.fail_with = None
    r = client.post(f"/api/messages/{failed['id']}/regenerate", json={})
    kind, data = sse(r)[-2]
    assert kind == "done" and data["message"]["id"] == failed["id"] and data["message"]["error"] is None
    assert len(client.get(f"/api/chats/{setup['chat']['id']}").json()["messages"]) == 2


def test_no_connection_and_keep_local_guard(client, owner, model):
    kb = owner["default_kb_id"]
    chat = client.post("/api/chats", json={"kb_id": kb}).json()
    r = client.post(f"/api/chats/{chat['id']}/messages", json={"content": "hi?"})
    assert r.status_code == 409 and "API keys" in r.json()["detail"]

    cloud = client.post("/api/connections", json={"api_base": "https://api.anthropic.com/v1", "api_key": "sk-ant-api03-good-4f1c"})
    # The mock /models answers for any host.
    assert cloud.status_code == 201, cloud.text
    r = client.post(f"/api/chats/{chat['id']}/messages", json={"content": "hi?", "connection_id": cloud.json()["id"]})
    assert r.status_code == 409 and "Keep local knowledge bases local" in r.json()["detail"]

    with SessionLocal() as db:
        db.get(WorkspaceSettings, owner["workspace_id"]).keep_local = False
        db.commit()
    upload(client, kb, ("Acme_MSA.pdf", MSA, "application/pdf"))
    queue.process_all()
    evs = ask(client, chat["id"], "How much notice to terminate?", connection_id=cloud.json()["id"], model="claude-sonnet-4-5")
    msg = evs[-2][1]["message"]
    assert msg["model"] == "claude-sonnet-4-5" and msg["runtime"] == "cloud" and msg["citations"]


def test_chat_isolation_and_delete(app, client, setup):
    from tests.conftest import make_client

    with make_client(app) as anon:
        assert anon.get(f"/api/chats/{setup['chat']['id']}").status_code == 401
    assert client.delete(f"/api/chats/{setup['chat']['id']}").status_code == 204
    assert client.get(f"/api/chats/{setup['chat']['id']}").status_code == 404


def test_parse_followups_is_lenient():
    assert answer.parse_followups('Sure! ["A thing", "B thing?"]', "q") == ["A thing?", "B thing?"]
    assert answer.parse_followups("1. First one\n2. Second one", "q") == ["First one?", "Second one?"]
    assert answer.parse_followups('["q"]', "q") == []


def test_prompt_instructions_are_saved_and_used_without_restart(client, setup, model, owner):
    s = client.get("/api/settings").json()
    assert s["custom_instructions"] == "" and s["can_edit"] and "cite the passage number" in s["built_in_prompt"]

    r = client.patch("/api/settings", json={"custom_instructions": "  Answer as a numbered list.  "})
    assert r.status_code == 200 and r.json()["custom_instructions"] == "Answer as a numbered list."

    model.requests.clear()
    ask(client, setup["chat"]["id"], "How much notice to terminate?")
    system = next(r for r in model.requests if "Question:" in r["messages"][-1]["content"])["messages"][0]["content"]
    assert system.startswith(answer.SYSTEM)
    assert "Additional instructions from this workspace" in system and "Answer as a numbered list." in system

    client.patch("/api/settings", json={"custom_instructions": ""})
    model.requests.clear()
    ask(client, setup["chat"]["id"], "How much notice to terminate?")
    system = next(r for r in model.requests if "Question:" in r["messages"][-1]["content"])["messages"][0]["content"]
    assert "Additional instructions" not in system

    titles = [e.title for e in SessionLocal().scalars(select(Event).where(Event.category == "settings"))]
    assert titles == ["Prompt instructions updated", "Prompt instructions cleared"]
    assert client.patch("/api/settings", json={"custom_instructions": "x" * 4001}).status_code == 422


def test_only_owner_edits_prompt(app, client, owner, monkeypatch):
    from app.config import get_settings
    from tests.conftest import PASSWORD, make_client

    monkeypatch.setenv("ALLOW_SIGNUP", "true")
    get_settings.cache_clear()
    with make_client(app) as member:
        member.post("/api/auth/signup", json={"name": "Bo", "email": "bo@example.com", "password": PASSWORD})
        assert member.get("/api/settings").json()["can_edit"] is False
        assert member.patch("/api/settings", json={"custom_instructions": "hi"}).status_code == 403
