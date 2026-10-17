"""Company search for the ticker boxes: a bundled NSE list, searched as you type, with a
live Yahoo Finance lookup for companies that are not in it.

data/nse_companies.csv holds about 280 widely held NSE stocks. Running
scripts/update_symbols.py replaces it with NSE's full list of listed equities.
"""
from __future__ import annotations

import csv
import re
import threading
from pathlib import Path

import config
from tools.base import cached

LIST_PATH = config.BASE_DIR / "data" / "nse_companies.csv"

# What people type instead of the symbol.
ALIASES = {
    "SBI": "SBIN", "HUL": "HINDUNILVR", "L&T": "LT", "LNT": "LT", "AIRTEL": "BHARTIARTL",
    "ZOMATO": "ETERNAL", "HDFC": "HDFCBANK", "KOTAK": "KOTAKBANK", "BAJAJ FINANCE": "BAJFINANCE",
    "MAHINDRA": "M&M", "M AND M": "M&M", "DMART": "DMART", "LIC": "LICI", "INDIGO": "INDIGO",
    "VODAFONE": "IDEA", "VI": "IDEA", "TITAN": "TITAN", "MINDTREE": "LTIM", "JIO": "JIOFIN",
}

_lock = threading.Lock()
_companies: list[dict] | None = None


def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip()


def companies() -> list[dict]:
    """[{symbol, name}] from the bundled CSV (NSE's own EQUITY_L.csv columns work too)."""
    global _companies
    with _lock:
        if _companies is None:
            rows = []
            if Path(LIST_PATH).exists():
                with open(LIST_PATH, newline="", encoding="utf-8-sig") as f:
                    for r in csv.DictReader(f):
                        r = {k.strip().upper(): (v or "").strip() for k, v in r.items() if k}
                        sym, name = r.get("SYMBOL"), r.get("NAME OF COMPANY") or r.get("NAME")
                        if sym and name:
                            rows.append({"symbol": sym.upper(), "name": _clean_name(name)})
            _companies = rows
        return _companies


def name_for(symbol: str) -> str | None:
    symbol = (symbol or "").upper()
    for c in companies():
        if c["symbol"] == symbol:
            return c["name"]
    return None


def _score(q: str, c: dict) -> int:
    sym, name = c["symbol"], c["name"].upper()
    if sym == q:
        return 100
    if sym.startswith(q) or name.startswith(q):
        return 85
    words = re.split(r"[\s().&-]+", name)
    if any(w.startswith(q) for w in words if w):
        return 65
    if len(q) >= 3 and q in sym:
        return 50
    if len(q) >= 3 and q in name:
        return 40
    return 0


def search(query: str, limit: int = 8) -> list[dict]:
    q = re.sub(r"\s+", " ", (query or "").strip().upper())
    if q.endswith((".NS", ".BO")):
        q = q[:-3]
    if not q:
        return []
    scored = []
    alias = ALIASES.get(q)
    for rank, c in enumerate(companies()):     # the list is ordered roughly by size
        s = 95 if alias and c["symbol"] == alias else _score(q, c)
        if s:
            scored.append((s, rank, c))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{**c, "source": "list"} for _, _, c in scored[:limit]]


def live_search(query: str, limit: int = 6) -> list[dict]:
    """NSE matches from Yahoo Finance's search (for companies outside the bundled list).
    Returns [] on any failure: suggestions are a convenience, never an error."""
    q = (query or "").strip()
    if len(q) < 3:
        return []

    def _load():
        try:
            import yfinance as yf
            quotes = yf.Search(q, max_results=15, news_count=0).quotes or []
        except Exception:
            return []
        out = []
        for item in quotes:
            sym = str(item.get("symbol") or "")
            if not sym.endswith(".NS"):
                continue
            name = item.get("longname") or item.get("shortname") or sym
            out.append({"symbol": sym[:-3].upper(), "name": _clean_name(str(name)), "source": "live"})
        return out

    return cached(("symbol-search", q.lower()), _load, ttl=24 * 3600)[:limit]


def suggest(query: str, limit: int = 8) -> list[dict]:
    """Bundled matches; a live lookup when the bundled list has none."""
    found = search(query, limit)
    if not found:                       # live lookup only when the bundled list has nothing
        seen = {c["symbol"] for c in found}
        for c in live_search(query):
            if c["symbol"] not in seen:
                found.append(c)
                seen.add(c["symbol"])
    return found[:limit]


def close_matches(query: str, limit: int = 3) -> list[dict]:
    """Likely intended companies for a symbol that does not exist (typos, partial names)."""
    import difflib
    q = (query or "").strip().upper()
    found = search(q, limit)
    if found:
        return found
    by_symbol = {c["symbol"]: c for c in companies()}
    names = difflib.get_close_matches(q, list(by_symbol), n=limit, cutoff=0.6)
    return [{**by_symbol[n], "source": "list"} for n in names]
