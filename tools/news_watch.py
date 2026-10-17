"""Headlines for the watchlist: only ones about this company, with their age, tone and
whether they are the kind of news that moves a share price."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from tools import news_data
from tools.base import ToolError
from tools.safety import is_suspicious

# Words that mark price-moving news: results, deals, regulator action, ratings, management.
MATERIAL = re.compile(
    r"\b(results?|earnings|q[1-4]|quarter|profit|revenue|guidance|order|orders|contract|deal|"
    r"acquisition|acquire|acquires|merger|demerger|stake|block deal|bulk deal|dividend|bonus|"
    r"split|buyback|rights issue|qip|ipo|sebi|rbi|penalty|probe|raid|fraud|default|downgrade|"
    r"upgrade|target price|rating|resigns?|ceo|cfo|chairman|ban|recall|plunges?|surges?|"
    r"slumps?|jumps?|soars?|crash|record high|52-week|lower circuit|upper circuit)\b", re.I)

_STOP = {"LIMITED", "LTD", "INDIA", "OF", "THE", "AND", "&", "COMPANY", "CORPORATION", "INDUSTRIES",
         "BANK", "(INDIA)", "SERVICES", "ENTERPRISES"}


def name_keys(ticker: str, name: str | None) -> list[str]:
    """Words a relevant headline must contain: the symbol or a distinctive part of the name."""
    keys = [ticker]
    if name:
        words = [w for w in re.split(r"[\s,()]+", name.upper()) if w and w not in _STOP]
        if words:
            keys.append(words[0])
            if len(words) > 1 and len(words[0]) <= 4:
                keys.append(" ".join(words[:2]))
        bracket = re.search(r"\(([^)]+)\)", name)
        if bracket:
            keys.append(bracket.group(1).upper())
    return [k for k in dict.fromkeys(keys) if len(k) >= 2]


def _age_hours(published: str | None) -> float | None:
    if not published:
        return None
    try:
        dt = parsedate_to_datetime(published)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)


def company_news(ticker: str, name: str | None = None, max_age_hours: float = 30) -> list[dict]:
    """Recent relevant headlines, newest first: [{title, source, link, ageHours, tone, material}].
    Returns [] when no news source answers."""
    query = f"{(name or ticker).split('(')[0].replace('Limited', '').strip()} share"
    items = []
    for source in news_data.SOURCES:
        try:
            items = news_data.get_headlines(query, source)
            break
        except ToolError:
            continue
    keys = name_keys(ticker, name)
    pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b", re.I)
    out, seen = [], set()
    for it in items:
        title = re.sub(r"\s+-\s+[^-]+$", "", it.get("title") or "").strip()  # drop " - Publisher"
        if not title or title.lower() in seen or not pattern.search(title) or is_suspicious(title):
            continue
        age = _age_hours(it.get("published"))
        if age is not None and age > max_age_hours:
            continue
        seen.add(title.lower())
        tone = news_data.keyword_sentiment([title])["newsSentiment"]
        if tone == "Neutral":   # a single clear word is enough for one headline
            pos, neg = (len(news_data._POS.findall(title)), len(news_data._NEG.findall(title)))
            tone = "Positive" if pos > neg else "Negative" if neg > pos else "Neutral"
        out.append({"title": title, "source": it.get("source"), "link": it.get("link"),
                    "ageHours": age, "tone": tone, "material": bool(MATERIAL.search(title))})
    out.sort(key=lambda x: x["ageHours"] if x["ageHours"] is not None else 99)
    return out
