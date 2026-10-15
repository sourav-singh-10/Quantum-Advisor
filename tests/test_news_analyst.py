from agents.news_agent import NewsAnalyst
from tests.agent_helpers import make_ctx
from tests.fakes import patch_data

HEADLINES = ["Testco wins large order", "Testco CFO resigns amid probe", "Markets close flat"]


def test_llm_labels_each_headline(monkeypatch, tmp_path):
    patch_data(monkeypatch, headlines=HEADLINES)
    ctx, _ = make_ctx(tmp_path, {("NewsAnalyst", "NewsView"): [{
        "labels": [{"index": 0, "sentiment": "Positive", "material": True},
                   {"index": 1, "sentiment": "Negative", "material": True},
                   {"index": 2, "sentiment": "Neutral", "material": False}],
        "overall": "Negative", "summary": "The probe outweighs the order."}]})
    out = NewsAnalyst().run(ctx, "TESTCO")
    assert out["newsSentiment"] == "Negative" and out["sentimentScore"] == -1
    assert out["materialHeadlines"] == HEADLINES[:2]


def test_falls_back_to_keywords_without_llm(monkeypatch, tmp_path):
    patch_data(monkeypatch, headlines=["Testco shares plunge after fraud probe"])
    ctx, _ = make_ctx(tmp_path, available=False)
    assert NewsAnalyst().run(ctx, "TESTCO")["newsSentiment"] == "Negative"


def test_no_news_source_is_not_fatal(monkeypatch, tmp_path):
    patch_data(monkeypatch, headlines=None)
    ctx, _ = make_ctx(tmp_path, available=False)
    out = NewsAnalyst().run(ctx, "TESTCO")
    assert out["newsAvailable"] is False and out["sentimentScore"] == 0
