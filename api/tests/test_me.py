from app.security.crypto import decrypt, encrypt, mask_key
from app.security.useragent import describe
from tests.conftest import PASSWORD, make_client
from tests.test_auth import events

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"


def test_patch_me_updates_profile_and_theme(client, owner):
    r = client.patch("/api/me", json={"name": "Ada L.", "theme": "dark"})
    assert r.status_code == 200
    assert r.json()["name"] == "Ada L." and r.json()["theme"] == "dark"
    assert [e.title for e in events("settings")] == ["Profile updated"]
    # Theme-only change is not a profile event.
    client.patch("/api/me", json={"theme": "light"})
    assert len(events("settings")) == 1


def test_patch_me_rejects_unknown_kb_and_bad_theme(client, owner):
    assert client.patch("/api/me", json={"default_kb_id": "nope"}).status_code == 404
    assert client.patch("/api/me", json={"theme": "purple"}).status_code == 422


def test_change_password(app, client, owner):
    bad = client.post("/api/me/password", json={"current": "wrong-one-xx", "new": "another-password-1"})
    assert bad.status_code == 400
    short = client.post("/api/me/password", json={"current": PASSWORD, "new": "short"})
    assert short.status_code == 422
    ok = client.post("/api/me/password", json={"current": PASSWORD, "new": "another-password-1"})
    assert ok.status_code == 204
    with make_client(app) as c:
        assert c.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 401
        assert c.post("/api/auth/login", json={"email": "ada@example.com", "password": "another-password-1"}).status_code == 200
    assert "Password changed" in [e.title for e in events("login")]


def test_sessions_list_and_revoke(app, client, owner):
    with make_client(app, ua=IPHONE) as phone, make_client(app) as laptop:
        phone.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
        laptop.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})

        sessions = client.get("/api/me/sessions").json()
        assert len(sessions) == 3
        assert sum(s["current"] for s in sessions) == 1
        phone_s = next(s for s in sessions if s["device"] == "Safari on iPhone")

        current = next(s for s in sessions if s["current"])
        assert client.delete(f"/api/me/sessions/{current['id']}").status_code == 400

        assert client.delete(f"/api/me/sessions/{phone_s['id']}").status_code == 204
        assert phone.get("/api/me").status_code == 401
        assert laptop.get("/api/me").status_code == 200

        assert client.delete("/api/me/sessions?others=true").status_code == 204
        assert laptop.get("/api/me").status_code == 401
        assert client.get("/api/me").status_code == 200
        assert len(client.get("/api/me/sessions").json()) == 1

    titles = [e.title for e in events("login")]
    assert "Session signed out" in titles
    assert "Signed out all other sessions" in titles


def test_sole_owner_cannot_delete_account(client, owner):
    r = client.delete("/api/me")
    assert r.status_code == 409
    assert client.get("/api/me").status_code == 200


def test_member_can_delete_account(app, owner, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("ALLOW_SIGNUP", "true")
    get_settings.cache_clear()
    with make_client(app) as c:
        c.post("/api/auth/signup", json={"name": "Bo", "email": "bo@example.com", "password": PASSWORD})
        assert c.delete("/api/me").status_code == 204
        assert c.get("/api/me").status_code == 401
        assert c.post("/api/auth/login", json={"email": "bo@example.com", "password": PASSWORD}).status_code == 401


def test_crypto_roundtrip_and_mask(app):
    token = encrypt("sk-ant-api03-abcdefgh4f1c")
    assert "sk-ant" not in token
    assert decrypt(token) == "sk-ant-api03-abcdefgh4f1c"
    assert mask_key("sk-ant-api03-abcdefgh4f1c") == "sk-ant-…4f1c"
    assert mask_key("ollama") == "••••••••"


def test_useragent_describe():
    assert describe(IPHONE) == "Safari on iPhone"
    assert describe("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36 Edg/128.0") == "Edge on Windows"
    assert describe(None) == "Unknown device"
