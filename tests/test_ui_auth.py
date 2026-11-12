"""Interface de suivi : authentification, anti-CSRF, droits, interrupteur, garde du mode démo."""
import pytest
from fastapi.testclient import TestClient

import main
from config import settings
from store import MemoryStore
from ui.auth import COOKIE, hash_password, parse_users, verify_password


class FakeSessions:
    def __init__(self):
        self.tokens, self.failures = {}, {}

    async def create(self, login, role):
        token = f"t-{login}"
        self.tokens[token] = {"login": login, "role": role}
        return token

    async def get(self, token):
        return self.tokens.get(token)

    async def delete(self, token):
        self.tokens.pop(token, None)

    async def too_many_failures(self, login):
        return self.failures.get(login, 0) >= 5

    async def record_failure(self, login):
        self.failures[login] = self.failures.get(login, 0) + 1


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "UI_USERS",
                        f"chef:admin:{hash_password('pw-admin')},dev:lecteur:{hash_password('pw-dev')}")
    store = MemoryStore()
    main.app.state.sessions, main.app.state.store = FakeSessions(), store
    c = TestClient(main.app)
    c.store = store
    return c


def login(c, user, pwd):
    return c.post("/ui/api/login", json={"login": user, "password": pwd})


def test_password_hash_roundtrip():
    h = hash_password("secret-x")
    assert verify_password("secret-x", h) and not verify_password("autre", h)
    assert not verify_password("x", "pas-une-empreinte")
    assert parse_users(f"a:admin:{h}")["a"][0] == "admin"
    with pytest.raises(ValueError):
        parse_users(f"a:superuser:{h}")


def test_everything_requires_a_session(client):
    for path in ("/ui/api/me", "/ui/api/runs", "/ui/api/stats", "/ui/api/config"):
        assert client.get(path).status_code == 401, path


def test_login_sets_httponly_cookie_and_rejects_bad_password(client):
    assert login(client, "dev", "faux").status_code == 401
    r = login(client, "dev", "pw-dev")
    assert r.status_code == 200 and r.json() == {"login": "dev", "role": "lecteur"}
    cookie = r.headers["set-cookie"].lower()
    assert COOKIE in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/ui/api/me").json()["login"] == "dev"


def test_login_is_throttled(client):
    for _ in range(5):
        login(client, "dev", "faux")
    assert login(client, "dev", "pw-dev").status_code == 429


def test_kill_switch_is_admin_only_and_needs_csrf_header(client):
    login(client, "dev", "pw-dev")
    hdr = {"X-Requested-With": "calipso-ui"}
    assert client.put("/ui/api/publishing", json={"enabled": False}, headers=hdr).status_code == 403
    login(client, "chef", "pw-admin")
    assert client.put("/ui/api/publishing", json={"enabled": False}).status_code == 403  # sans en-tête
    r = client.put("/ui/api/publishing", json={"enabled": False}, headers=hdr)
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert client.store.history == [{"enabled": False, "by": "chef"}]


def test_demo_is_refused_against_real_github(client, monkeypatch):
    login(client, "chef", "pw-admin")
    hdr = {"X-Requested-With": "calipso-ui"}
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert client.post("/ui/api/demo/launch", json={"prs": [101]}, headers=hdr).status_code == 404
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "GITHUB_API_URL", "https://api.github.com")
    assert client.post("/ui/api/demo/launch", json={"prs": [101]}, headers=hdr).status_code == 409
