import json

import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ProviderConnection
from app.providers import catalog
from app.providers.auto import pick_auto
from app.providers.base import display_name, runtime_for
from tests.test_auth import events

LMSTUDIO = "http://host.docker.internal:1234/v1"
LM_MODELS = ["text-embedding-nomic-embed-text-v1.5", "google/gemma-4-e2b", "qwen/qwen3.5-9b", "qwen2.5-vl-7b"]


@pytest.fixture
def provider(monkeypatch):
    """Fake provider APIs. Records requests; behaviour depends on host and key."""
    seen: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        host = req.url.host
        if host == "down.example":
            raise httpx.ConnectError("refused", request=req)
        if host == "api.anthropic.com":
            if req.headers.get("x-api-key") != "sk-ant-api03-good-4f1c":
                return httpx.Response(401, json={"error": "bad key"})
            return httpx.Response(200, json={"data": [{"id": "claude-sonnet-4-5"}, {"id": "claude-haiku-4-5"}]})
        if host == "api.openai.com":
            if req.headers.get("authorization") != "Bearer sk-good":
                return httpx.Response(401)
            return httpx.Response(200, json={"data": [{"id": "gpt-4.1"}, {"id": "text-embedding-3-small"}]})
        if host == "html.example":
            return httpx.Response(200, text="<html>hi</html>")
        if req.url.path.endswith("/v1/models"):
            return httpx.Response(200, json={"object": "list", "data": [{"id": m} for m in LM_MODELS]})
        return httpx.Response(404)

    monkeypatch.setattr(catalog, "transport", httpx.MockTransport(handle))
    return seen


def test_add_local_connection_without_key(client, owner, provider):
    r = client.post("/api/connections", json={"api_base": LMSTUDIO + "/", "api_key": ""})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["name"] == "LM Studio"
    assert c["api_base"] == LMSTUDIO  # trailing slash trimmed
    assert c["runtime"] == "local"
    assert c["models"] == LM_MODELS
    assert "text-embedding-nomic-embed-text-v1.5" not in c["chat_models"]
    assert c["selected_model"] == "auto"
    assert c["resolved_model"] == "qwen/qwen3.5-9b"  # qwen3.5* beats gemma* in the default preference
    assert c["masked_key"] == "No key"
    assert "authorization" not in provider[0].headers


def test_add_cloud_connection_encrypts_key_and_masks_it(client, owner, provider):
    r = client.post("/api/connections", json={"api_base": "https://api.anthropic.com/v1", "api_key": "sk-ant-api03-good-4f1c"})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["name"] == "Anthropic" and c["kind"] == "anthropic" and c["runtime"] == "cloud"
    assert c["masked_key"] == "sk-ant-…4f1c"
    assert c["resolved_model"] == "claude-sonnet-4-5"
    assert provider[0].headers["anthropic-version"]
    with SessionLocal() as db:
        row = db.scalar(select(ProviderConnection))
        assert "sk-ant" not in row.api_key_enc
    listed = client.get("/api/connections").json()
    assert "sk-ant-api03-good-4f1c" not in json.dumps(listed)
    ev = [e for e in events("key")]
    assert ev[0].title == "Provider connected" and "Anthropic" in ev[0].detail


@pytest.mark.parametrize(
    ("body", "code", "message"),
    [
        ({"api_base": "ftp://x", "api_key": "k"}, 422, "must start with http"),
        ({"api_base": "https://api.openai.com/v1", "api_key": ""}, 422, "Enter an API key"),
        ({"api_base": "https://api.openai.com/v1", "api_key": "sk-wrong"}, 400, "rejected this API key"),
        ({"api_base": "http://down.example/v1", "api_key": "k"}, 400, "Couldn't reach down.example"),
        ({"api_base": "http://nope.example/api", "api_key": "k"}, 400, "No models endpoint"),
        ({"api_base": "http://html.example/v1", "api_key": "k"}, 400, "wasn't JSON"),
    ],
)
def test_add_connection_errors(client, owner, provider, body, code, message):
    r = client.post("/api/connections", json=body)
    assert r.status_code == code, r.text
    assert message in r.json()["detail"]
    assert client.get("/api/connections").json() == []


def test_duplicate_base_rejected(client, owner, provider):
    assert client.post("/api/connections", json={"api_base": LMSTUDIO}).status_code == 201
    assert client.post("/api/connections", json={"api_base": LMSTUDIO + "/"}).status_code == 409


def test_select_model_refresh_and_remove(client, owner, provider):
    cid = client.post("/api/connections", json={"api_base": LMSTUDIO}).json()["id"]

    assert client.patch(f"/api/connections/{cid}", json={"selected_model": "not-a-model"}).status_code == 422
    r = client.patch(f"/api/connections/{cid}", json={"selected_model": "google/gemma-4-e2b"})
    assert r.status_code == 200
    assert r.json()["selected_model"] == r.json()["resolved_model"] == "google/gemma-4-e2b"

    r = client.post(f"/api/connections/{cid}/refresh")
    assert r.status_code == 200 and r.json()["selected_model"] == "google/gemma-4-e2b"

    assert client.delete(f"/api/connections/{cid}").status_code == 204
    assert client.get("/api/connections").json() == []
    titles = [e.title for e in events("key")]
    assert titles == ["Provider connected", "Model changed", "Provider removed"]
    changed = [e for e in events("key") if e.title == "Model changed"][0]
    assert changed.detail == "LM Studio · Auto → google/gemma-4-e2b"


def test_test_endpoint_does_not_save(client, owner, provider):
    r = client.post("/api/connections/test", json={"api_base": LMSTUDIO})
    assert r.status_code == 200 and r.json()["models"] == LM_MODELS
    assert client.get("/api/connections").json() == []


def test_requires_auth(app, provider):
    from tests.conftest import make_client

    with make_client(app) as anon:
        assert anon.get("/api/connections").status_code == 401
        assert anon.post("/api/connections", json={"api_base": LMSTUDIO}).status_code == 401


def test_helpers():
    assert display_name("http://localhost:11434/v1") == "Ollama"
    assert display_name("https://openrouter.ai/api/v1") == "OpenRouter"
    assert display_name("https://llm.example.com/v1") == "llm.example.com"
    assert runtime_for("http://192.168.56.1:1234/v1") == "local"
    assert runtime_for("https://api.openai.com/v1") == "cloud"
    assert pick_auto(["text-embedding-3-small", "gpt-4o", "gpt-4.1-mini"], ["gpt-4.1*"]) == "gpt-4.1-mini"
    assert pick_auto(["mystery-model"], ["gpt-4.1*"]) == "mystery-model"
    assert pick_auto(["nomic-embed-text"], []) == "nomic-embed-text"
    assert pick_auto([], []) is None


def test_reencrypt_keys_after_secret_change(client, owner):
    import argparse

    from app import cli
    from app.db import SessionLocal
    from app.models import ProviderConnection
    from app.security.crypto import _fernet, decrypt

    r = client.post("/api/connections", json={"api_base": "http://localhost:1234/v1", "api_key": "lm-key-123"})
    assert r.status_code == 201
    with SessionLocal() as db:  # simulate a key saved under the previous APP_SECRET
        c = db.get(ProviderConnection, r.json()["id"])
        c.api_key_enc = _fernet("old-secret").encrypt(b"lm-key-123").decode()
        db.commit()
    cli.reencrypt_keys(argparse.Namespace(old_secret="old-secret"))
    with SessionLocal() as db:
        assert decrypt(db.get(ProviderConnection, r.json()["id"]).api_key_enc) == "lm-key-123"
