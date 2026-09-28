import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.security.ratelimit import login_limiter

PASSWORD = "correct-horse-battery"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("ALLOW_SIGNUP", "false")
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.setenv("WEB_DIST", str(tmp_path / "no-dist"))
    get_settings.cache_clear()
    login_limiter.reset()

    from app.main import create_app

    yield create_app()
    get_settings.cache_clear()


def make_client(app, ua: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Chrome/128.0 Safari/537.36") -> TestClient:
    return TestClient(app, headers={"X-Requested-With": "fetch", "User-Agent": ua})


@pytest.fixture
def client(app):
    with make_client(app) as c:
        yield c


@pytest.fixture
def owner(client):
    r = client.post("/api/auth/signup", json={"name": "Ada Owner", "email": "ada@example.com", "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()
