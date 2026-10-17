import io

from agents.portfolio_review_agent import PortfolioReviewAgent
from tests.agent_helpers import make_ctx
from tests.test_portfolio import CSV, fake_quote
from tools.portfolio_analyzer import PortfolioAnalyzer


def analysis():
    return PortfolioAnalyzer(quote_fn=fake_quote).analyze_portfolio(io.BytesIO(CSV), "h.csv")


def test_rule_review_without_llm(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    out = PortfolioReviewAgent().run(ctx, analysis())
    assert out["degraded"] is True and len(out["holdings"]) == 3 and out["actions"]


def test_llm_review_and_add_guardrail(tmp_path):
    ctx, llm = make_ctx(tmp_path, {("PortfolioReviewAgent", "PortfolioReview"): [{
        "summary": "Concentrated in two names.",
        "actions": ["Trim BBB", "Check ZZZ"],
        "holdings": [{"ticker": "AAA", "action": "HOLD", "reason": "up 50%"},
                     {"ticker": "BBB", "action": "TRIM", "reason": "volatile and expensive"},
                     {"ticker": "ZZZ", "action": "ADD", "reason": "cheap"}]}]})
    out = PortfolioReviewAgent().run(ctx, analysis())
    calls = {h["ticker"]: h["action"] for h in out["holdings"]}
    assert calls == {"AAA": "HOLD", "BBB": "TRIM", "ZZZ": "REVIEW"}   # no ADD without a live price
    assert "live (yfinance)" in llm.calls[0][2]                       # the LLM saw the price source


def test_upload_endpoint_returns_review_and_trace(monkeypatch):
    import config
    import app as app_module
    from tests.fakes import FUNDAMENTALS, patch_data
    monkeypatch.setattr(config, "REQUIRE_LOGIN", False)
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS)
    app_module.init_db()
    client = app_module.app.test_client()
    res = client.post("/upload_portfolio", data={"file": (io.BytesIO(b"ticker,quantity,buy_price\nTESTCO,10,90\n"), "h.csv")},
                      content_type="multipart/form-data")
    body = res.get_json()
    assert res.status_code == 200 and body["stocks"][0]["priceSource"].startswith("live")
    assert body["review"]["holdings"][0]["ticker"] == "TESTCO"
    types = [e["type"] for e in body["trace"]]
    assert types[0] == "request" and "tool_call" in types and types[-1] == "final"
