import pytest


@pytest.fixture
def client(monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", True)
    import app as app_module
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    c = app_module.app.test_client()
    assert c.post("/signup", json={"email": "p@q.in", "password": "secret1"}).status_code == 200
    return c


def test_pages_are_routed(client):
    assert b"<title>" in client.get("/").data              # public home page
    assert client.get("/app").status_code == 200
    assert client.get("/no-such-page").status_code == 404
    assert client.get("/api/nothing").get_json() == {"error": "Not found"}


def test_profile_defaults_then_save_and_read(client):
    first = client.get("/api/profile").get_json()
    assert first["saved"] is False and first["profile"]["age"] == 30
    saved = client.put("/api/profile", json={"age": 41, "experience": "Experienced",
                                             "riskAppetite": "Conservative", "portfolioValue": 250000,
                                             "timeHorizon": "Long-term", "goal": "Child's education"})
    assert saved.status_code == 200
    again = client.get("/api/profile").get_json()
    assert again["saved"] is True and again["profile"]["goal"] == "Child's education"


def test_profile_is_validated(client):
    res = client.put("/api/profile", json={"age": 7})
    assert res.status_code == 400 and res.get_json()["details"][0]["field"] == "age"


def test_profile_needs_sign_in(client):
    client.post("/logout")
    assert client.get("/api/profile").status_code == 401


def test_change_password(client):
    assert client.post("/api/account/password", json={"current": "wrong", "new": "newsecret"}).status_code == 403
    assert client.post("/api/account/password", json={"current": "secret1", "new": "abc"}).status_code == 400
    assert client.post("/api/account/password", json={"current": "secret1", "new": "newsecret"}).status_code == 200
    client.post("/logout")
    assert client.post("/login", json={"email": "p@q.in", "password": "secret1"}).status_code == 401
    assert client.post("/login", json={"email": "p@q.in", "password": "newsecret"}).status_code == 200


def test_profile_keeps_goals_monthly_amount_and_avoid_list(client):
    body = {"age": 35, "portfolioValue": 300000, "monthlyInvest": 10000,
            "goals": [{"title": " Daughter's college ", "amount": 2000000, "year": 2032},
                      {"title": "Retirement"}],
            "avoidSectors": ["Tobacco", "Tobacco", "Alcohol"]}
    p = client.put("/api/profile", json=body).get_json()["profile"]
    assert p["goals"][0] == {"title": "Daughter's college", "amount": 2000000, "year": 2032}
    assert p["monthlyInvest"] == 10000 and p["avoidSectors"] == ["Tobacco", "Alcohol"]
    assert client.get("/api/profile").get_json()["profile"]["goals"][1]["title"] == "Retirement"


@pytest.mark.parametrize("bad,field", [
    ({"avoidSectors": ["Crypto"]}, "avoidSectors"),
    ({"goals": [{"title": "   "}]}, "goals"),
    ({"goals": [{"title": "x", "year": 1990}]}, "goals"),
    ({"goals": [{"title": str(i)} for i in range(5)]}, "goals"),
])
def test_profile_extras_are_validated(client, bad, field):
    res = client.put("/api/profile", json=bad)
    assert res.status_code == 400 and res.get_json()["details"][0]["field"].startswith(field)


def test_welcome_page_is_served(client):
    assert b"Tell the committee about you" in client.get("/welcome.html").data


def test_avoided_company_is_flagged_without_changing_the_call(monkeypatch):
    from core.runner import run_analysis
    from core.schemas import AnalyzeRequest
    from tests.fakes import FUNDAMENTALS, FakeLLM, patch_data
    from tools.preferences import avoid_matches
    patch_data(monkeypatch, fundamentals={**FUNDAMENTALS, "sector": "Consumer Defensive",
                                          "name": "ITC Limited"}, headlines=["x"])
    plain = run_analysis(AnalyzeRequest(ticker="ITC").model_dump(), llm=FakeLLM(available=False))
    out = run_analysis(AnalyzeRequest(ticker="ITC", avoidSectors=["Tobacco"]).model_dump(),
                       llm=FakeLLM(available=False))
    assert plain["preferenceNotes"] == [] and "avoid tobacco" in out["preferenceNotes"][0]
    assert out["recommendation"] == plain["recommendation"]
    assert any(e["type"] == "decision" and "tobacco" in str(e["payload"]) for e in out["trace"])
    assert avoid_matches(["Alcohol"], "XYZ", "Beverages", "XYZ Breweries Ltd")       # matched by name


def test_google_sign_in_creates_then_reuses_the_account(monkeypatch):
    import config
    import app as app_module
    monkeypatch.setattr(config, "REQUIRE_LOGIN", True)
    app_module.init_db()
    c = app_module.app.test_client()
    assert c.post("/auth/google", json={"credential": "x"}).status_code == 400      # not configured
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    assert c.get("/api/auth/config").get_json()["googleClientId"].startswith("cid")

    def fake_verify(token):
        if token != "good":
            raise ValueError("bad token")
        return {"email": "Asha@Gmail.com", "email_verified": True, "given_name": "Asha"}
    monkeypatch.setattr(app_module, "verify_google_token", fake_verify)
    assert c.post("/auth/google", json={"credential": "forged"}).status_code == 401
    first = c.post("/auth/google", json={"credential": "good"}).get_json()
    assert first == {"ok": True, "email": "asha@gmail.com", "new": True}
    me = c.get("/me").get_json()
    assert me["loggedIn"] and me["authMethod"] == "google"
    assert c.get("/api/profile").get_json()["profile"]["name"] == "Asha"
    c.post("/logout")
    assert c.post("/auth/google", json={"credential": "good"}).get_json()["new"] is False
    c.post("/logout")
    res = c.post("/login", json={"email": "asha@gmail.com", "password": "anything"})
    assert res.status_code == 401 and "Google" in res.get_json()["error"]


def test_unverified_google_email_is_refused(monkeypatch):
    import config
    import app as app_module
    app_module.init_db()
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(app_module, "verify_google_token", lambda t: {"email": "x@y.z", "email_verified": False})
    assert app_module.app.test_client().post("/auth/google", json={"credential": "t"}).status_code == 401


def _cookie_expires(res):
    cookie = [h for h in res.headers.getlist("Set-Cookie") if h.startswith("session=")][0]
    return "Expires=" in cookie


def test_remember_me_controls_how_long_the_sign_in_lasts(client):
    client.post("/logout")
    kept = client.post("/login", json={"email": "p@q.in", "password": "secret1", "remember": True})
    assert kept.status_code == 200 and _cookie_expires(kept)          # lasts 30 days
    client.post("/logout")
    short = client.post("/login", json={"email": "p@q.in", "password": "secret1", "remember": False})
    assert short.status_code == 200 and not _cookie_expires(short)   # ends with the browser


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.ok = status, body, status == 200

    def json(self):
        return self._body


def test_google_popup_token_must_belong_to_this_app(monkeypatch):
    import requests
    import config
    import app as app_module
    app_module.init_db()
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    tokens = {
        "mine": {"aud": "cid.apps.googleusercontent.com", "expires_in": "3500", "email": "Ravi@Gmail.com", "email_verified": "true"},
        "other-app": {"aud": "someone-else", "expires_in": "3500", "email": "ravi@gmail.com", "email_verified": "true"},
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        if "tokeninfo" in url:
            t = tokens.get(params["access_token"])
            return _Resp(200, t) if t else _Resp(400, {})
        return _Resp(200, {"given_name": "Ravi"})
    monkeypatch.setattr(requests, "get", fake_get)
    c = app_module.app.test_client()
    assert c.post("/auth/google", json={"accessToken": "other-app"}).status_code == 401
    assert c.post("/auth/google", json={"accessToken": "nonsense"}).status_code == 401
    ok = c.post("/auth/google", json={"accessToken": "mine"})
    assert ok.status_code == 200 and ok.get_json()["email"] == "ravi@gmail.com"
