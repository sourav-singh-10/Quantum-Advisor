"""Session cookie flags, security headers and slowing down password guessing."""
import pytest


@pytest.fixture
def client(monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", True)
    import app as app_module
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    app_module._login_failures.clear()
    c = app_module.app.test_client()
    c.post("/signup", json={"email": "guard@test.in", "password": "secret1"})
    c.post("/logout")
    return c


def _session_cookie(res):
    return [h for h in res.headers.getlist("Set-Cookie") if h.startswith("session=")][0]


def test_session_cookie_is_http_only_and_same_site(client):
    res = client.post("/login", json={"email": "guard@test.in", "password": "secret1"})
    cookie = _session_cookie(res)
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_every_response_has_the_security_headers(client):
    for path in ("/", "/login.html", "/api/health", "/api/does-not-exist"):
        h = client.get(path).headers
        assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
        assert "Referrer-Policy" in h and "Permissions-Policy" in h


def test_repeated_wrong_passwords_are_locked_out_then_cleared(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "LOGIN_MAX_FAILURES", 3)
    wrong = {"email": "guard@test.in", "password": "nope"}
    assert [client.post("/login", json=wrong).status_code for _ in range(3)] == [401, 401, 401]
    locked = client.post("/login", json={"email": "guard@test.in", "password": "secret1"})
    assert locked.status_code == 429 and "Try again in" in locked.get_json()["error"]
    # the lockout is per email: another account from the same address can still sign in
    client.post("/signup", json={"email": "other@test.in", "password": "secret2"})
    client.post("/logout")
    assert client.post("/login", json={"email": "other@test.in", "password": "secret2"}).status_code == 200


def test_lockout_expires_and_a_success_resets_the_count(client, monkeypatch):
    import app as app_module
    import config
    monkeypatch.setattr(config, "LOGIN_MAX_FAILURES", 2)
    wrong = {"email": "guard@test.in", "password": "nope"}
    client.post("/login", json=wrong)
    assert client.post("/login", json={"email": "guard@test.in", "password": "secret1"}).status_code == 200
    client.post("/logout")
    assert client.post("/login", json=wrong).status_code == 401       # count started again from zero
    client.post("/login", json=wrong)
    assert client.post("/login", json=wrong).status_code == 429
    for times in app_module._login_failures.values():                 # pretend the window has passed
        times[:] = [t - (config.LOGIN_LOCKOUT_MINUTES * 60 + 1) for t in times]
    assert client.post("/login", json={"email": "guard@test.in", "password": "secret1"}).status_code == 200
