"""News tools: NewsAPI, Google News RSS (no key), and a word-boundary keyword scorer."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import requests

import config
from tools.base import ToolError, cached, http_get_json

# Generic words like "launch" or "orders" were dropped: in real headlines they are as
# often about other companies (or neutral) as good news for this one.
POSITIVE = ["surge", "surges", "soar", "soars", "rally", "rallies", "beat", "beats", "record",
            "profit", "profits", "growth", "upgrade", "upgraded", "bullish", "gain", "gains",
            "rise", "rises", "jumps", "outperform", "outperformed", "expansion", "dividend",
            "wins", "buy", "strong"]
NEGATIVE = ["fall", "falls", "drop", "drops", "plunge", "plunges", "miss", "misses", "loss",
            "losses", "decline", "declines", "downgrade", "downgraded", "weak", "bearish",
            "crash", "fraud", "lawsuit", "recall", "investigation", "penalty", "bankruptcy",
            "default", "layoff", "layoffs", "probe", "scandal", "slump", "slumps", "warning",
            "warns", "seize", "seizes", "seized", "charges", "allegations", "row", "risk",
            "risks", "pressure", "flat", "sell", "selloff", "sell-off", "lows", "cut", "cuts"]
_POS = re.compile(r"\b(" + "|".join(POSITIVE) + r")\b", re.I)
_NEG = re.compile(r"\b(" + "|".join(NEGATIVE) + r")\b", re.I)


def fetch_newsapi(query: str) -> list[dict]:
    if not config.NEWS_API_KEY:
        raise ToolError("NEWS_API_KEY not configured")
    data = http_get_json("https://newsapi.org/v2/everything",
                         {"q": query, "language": "en", "sortBy": "publishedAt",
                          "pageSize": 15, "apiKey": config.NEWS_API_KEY})
    if data.get("status") == "error":
        raise ToolError(f"NewsAPI: {data.get('message', 'error')}"[:200])
    items = [{"title": a.get("title") or "", "source": (a.get("source") or {}).get("name"),
              "published": a.get("publishedAt")} for a in data.get("articles", [])]
    items = [i for i in items if i["title"] and i["title"] != "[Removed]"]
    if not items:
        raise ToolError(f"NewsAPI found no articles for '{query}'")
    return items


def fetch_google_news_rss(query: str) -> list[dict]:
    try:
        response = requests.get("https://news.google.com/rss/search",
                                params={"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
                                timeout=config.HTTP_TIMEOUT_SECONDS)
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        raise ToolError(f"Google News RSS error: {type(exc).__name__}") from exc
    items = [{"title": (it.findtext("title") or "").strip(),
              "source": it.findtext("source"), "published": it.findtext("pubDate"),
              "link": (it.findtext("link") or "").strip() or None}
             for it in root.iter("item")][:15]
    if not items:
        raise ToolError(f"Google News found no articles for '{query}'")
    return items


# Google News RSS needs no key; NewsAPI free plan allows 100 requests a day.
_FETCHERS = {"google_rss": fetch_google_news_rss, "newsapi": fetch_newsapi}
SOURCES = tuple(_FETCHERS)


def get_headlines(query: str, source: str) -> list[dict]:
    source = (source or "").lower().strip()
    if source not in _FETCHERS:
        raise ToolError(f"unknown news source '{source}'; choose one of {', '.join(SOURCES)}")
    return cached(("news", source, query.lower()), lambda: _FETCHERS[source](query))


def keyword_sentiment(titles: list[str]) -> dict:
    """Fallback scorer used when the LLM is unavailable. Whole words only."""
    pos = sum(len(_POS.findall(t)) for t in titles)
    neg = sum(len(_NEG.findall(t)) for t in titles)
    # Only call it when one side clearly dominates; a near-tie is Neutral.
    if pos - neg >= 2 and pos >= 2 * neg:
        label, score = "Positive", 1
    elif neg - pos >= 2 and neg >= 2 * pos:
        label, score = "Negative", -1
    else:
        label, score = "Neutral", 0
    return {"newsSentiment": label, "sentimentScore": score,
            "positiveCount": pos, "negativeCount": neg}
