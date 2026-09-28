from sqlalchemy import select

from app.db import SessionLocal
from app.models import Event, KnowledgeBase, User
from tests.conftest import PASSWORD, make_client


def events(category: str | None = None) -> list[Event]:
    with SessionLocal() as db:
        q = select(Event).order_by(Event.created_at)
        if category:
            q = q.where(Event.category == category)
        return list(db.scalars(q))


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_unknown_api_route_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not found"}


def test_first_signup_becomes_owner_with_starter_kb(client, owner):
    assert owner["role"] == "owner"
    assert owner["theme"] == "light"
    assert owner["default_kb_id"]
    with SessionLocal() as db:
        kb = db.get(KnowledgeBase, owner["default_kb_id"])
        assert kb is not None and kb.name == "My documents" and kb.runtime == "local"
    me = client.get("/api/me")
    assert me.status_code == 200 and me.json()["email"] == "ada@example.com"


def test_password_is_hashed_with_argon2(owner):
    with SessionLocal() as db:
        u = db.scalar(select(User))
        assert u.password_hash.startswith("$argon2")
        assert PASSWORD not in u.password_hash


def test_signup_closed_after_first_user(app, owner):
    with make_client(app) as other:
        cfg = other.get("/api/auth/config").json()
        assert cfg == {"signup_open": False, "has_users": True, "public_host": "localhost:8000"}
        r = other.post("/api/auth/signup", json={"name": "Eve", "email": "eve@example.com", "password": PASSWORD})
        assert r.status_code == 403


def test_signup_open_when_allowed(app, owner, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("ALLOW_SIGNUP", "true")
    get_settings.cache_clear()
    with make_client(app) as other:
        r = other.post("/api/auth/signup", json={"name": "Bo", "email": "bo@example.com", "password": PASSWORD})
        assert r.status_code == 201 and r.json()["role"] == "member"
        dup = other.post("/api/auth/signup", json={"name": "Bo", "email": "BO@example.com", "password": PASSWORD})
        assert dup.status_code == 409


def test_signup_validates_password_length(client):
    r = client.post("/api/auth/signup", json={"name": "A", "email": "a@example.com", "password": "short"})
    assert r.status_code == 422


def test_login_logout_and_session_cookie(app, owner):
    with make_client(app) as c:
        assert c.get("/api/me").status_code == 401
        r = c.post("/api/auth/login", json={"email": "ADA@example.com ", "password": PASSWORD})
        assert r.status_code == 200
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        assert c.get("/api/me").status_code == 200
        assert c.post("/api/auth/logout").status_code == 204
        assert c.get("/api/me").status_code == 401
    titles = [e.title for e in events("login")]
    assert titles == ["Account created", "Signed in"]
    signed_in = events("login")[1]
    assert signed_in.detail.startswith("Chrome on macOS") and signed_in.tone == "ok"


def test_wrong_password_is_logged_and_rate_limited(app, owner):
    with make_client(app, ua="Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0") as c:
        for _ in range(5):
            assert c.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-password"}).status_code == 401
        r = c.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
        assert r.status_code == 429
    failed = [e for e in events("login") if e.title == "Failed sign-in attempt"]
    assert len(failed) == 6
    assert all(e.tag == "Blocked" and e.tone == "err" for e in failed)
    assert failed[0].detail == "Firefox on Linux · testclient · wrong password"


def test_unknown_email_gives_same_error(client, owner):
    r = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert r.status_code == 401
    assert r.json()["detail"] == "Email or password is incorrect."


def test_mutations_require_x_requested_with(app, owner):
    from fastapi.testclient import TestClient

    with TestClient(app) as bare:
        r = bare.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
        assert r.status_code == 403
        assert bare.get("/api/health").status_code == 200
