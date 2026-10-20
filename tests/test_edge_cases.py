"""Edge cases at the edges of the system: oversized uploads, a missing model key, and the
recorded run shown on the site staying identical to the committed trace."""
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", False)
    import app as app_module
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_oversized_document_gets_a_clear_413(client):
    big = io.BytesIO(b"%PDF-1.4\n" + b"0" * (16 * 1024 * 1024 + 10))
    res = client.post("/api/analyze", data={"ticker": "TCS", "document": (big, "huge.pdf")},
                      content_type="multipart/form-data")
    body = res.get_json()
    assert res.status_code == 413
    assert body["details"][0]["field"] == "document" and "15 MB" in body["details"][0]["message"]


def test_deep_health_check_reports_a_missing_model_key_without_failing(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    res = client.get("/api/health?deep=1")
    body = res.get_json()
    assert res.status_code == 200 and body["status"] == "ok"
    assert body["llmConfigured"] is False and body["llm"]["llmAvailable"] is False


def test_unknown_api_path_is_json_and_unknown_page_is_html(client):
    api = client.get("/api/does-not-exist")
    page = client.get("/does-not-exist")
    assert api.status_code == 404 and api.get_json() == {"error": "Not found"}
    assert page.status_code == 404 and b"<title>" in page.data


def test_terms_page_is_served_and_linked_from_sign_in(client):
    terms = client.get("/terms.html")
    assert terms.status_code == 200 and b"investment advice" in terms.data and b"SEBI" in terms.data
    for page in ("/login.html", "/signup.html"):
        assert b'href="terms.html"' in client.get(page).data


def test_recorded_run_on_the_site_is_the_committed_trace_unedited():
    """The home page and trace page replay frontend/samples/story_run.json; its events must be
    exactly the lines of the trace committed in docs/traces, so the replay cannot drift from it."""
    story = json.loads((ROOT / "frontend/samples/story_run.json").read_text(encoding="utf-8"))
    source = ROOT / story["source"]
    lines = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert story["events"] == sorted(lines, key=lambda e: e["seq"])
    assert story["messages"] == len(lines)
    seqs = {e["seq"] for e in lines}
    assert all(b["seq"] in seqs for b in story["beats"])
