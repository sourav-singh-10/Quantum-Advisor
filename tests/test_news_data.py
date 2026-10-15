import pytest

import config
from tools import news_data
from tools.base import ToolError
from tools.news_data import keyword_sentiment


def test_whole_words_only():
    # the CA2 scorer matched substrings: "enterprise" -> rise, "against" -> gain, "refinery" -> fine
    out = keyword_sentiment(["Enterprise refinery update against expectations"])
    assert out["positiveCount"] == 0 and out["negativeCount"] == 0


def test_negative_headlines():
    assert keyword_sentiment(["Shares plunge after fraud probe"])["sentimentScore"] == -1


def test_newsapi_errors_are_reported(monkeypatch):
    monkeypatch.setattr(config, "NEWS_API_KEY", "k")
    monkeypatch.setattr(news_data, "http_get_json",
                        lambda url, params: {"status": "error", "message": "rateLimited"})
    with pytest.raises(ToolError, match="rateLimited"):
        news_data.fetch_newsapi("TCS share")


def test_removed_articles_are_dropped(monkeypatch):
    monkeypatch.setattr(config, "NEWS_API_KEY", "k")
    monkeypatch.setattr(news_data, "http_get_json", lambda url, params: {"articles": [
        {"title": "[Removed]"}, {"title": "TCS wins order", "source": {"name": "ET"}}]})
    assert [i["title"] for i in news_data.fetch_newsapi("TCS")] == ["TCS wins order"]


def test_key_free_source_is_default():
    assert news_data.SOURCES[0] == "google_rss"
