"""How the committee's past calls turned out: the price one week and four weeks after each
analysis, and whether the call was borne out. A small sample is not proof of skill; the page
says so."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from tools.base import ToolError

IST = timezone(timedelta(hours=5, minutes=30))
WEEK, MONTH = 5, 20            # trading days
HOLD_BAND = 5.0                # a HOLD is borne out if the price stayed within +/-5%


def _pct(a, b):
    return round((a / b - 1) * 100, 2) if b else None


def judge(rec: str, ret: float | None) -> str | None:
    if ret is None:
        return None
    if rec == "BUY":
        return "right" if ret > 0 else "wrong"
    if rec == "SELL":
        return "right" if ret < 0 else "wrong"
    return "right" if abs(ret) <= HOLD_BAND else "wrong"


def outcome(run: dict, closes: list[float], dates: list[str]) -> dict:
    created = datetime.fromisoformat(run["created_at"]).astimezone(IST).date().isoformat()
    base = run.get("price")
    row = {"runId": run["run_id"], "ticker": run["ticker"], "date": created,
           "recommendation": run.get("recommendation"), "price": base,
           "after1w": None, "after4w": None, "now": None, "nowPct": None, "verdict": "too early"}
    if not base or not closes or len(dates) != len(closes):
        row["verdict"] = "no data"
        return row
    i = max((k for k, d in enumerate(dates) if d <= created), default=None)
    if i is None:
        row["verdict"] = "no data"
        return row
    row["now"], row["nowPct"] = round(closes[-1], 2), _pct(closes[-1], base)
    if i + WEEK < len(closes):
        row["after1w"] = _pct(closes[i + WEEK], base)
    if i + MONTH < len(closes):
        row["after4w"] = _pct(closes[i + MONTH], base)
        row["verdict"] = judge(row["recommendation"], row["after4w"])
    return row


def track_record(runs: list[dict], history_fn) -> dict:
    """``history_fn(ticker) -> (closes, volumes, dates)``; tickers are fetched once each."""
    tickers = sorted({r["ticker"] for r in runs})

    def load(t):
        try:
            closes, _vols, dates = history_fn(t)
            return t, (closes, dates)
        except ToolError:
            return t, ([], [])

    with ThreadPoolExecutor(max_workers=6) as pool:
        hist = dict(pool.map(load, tickers))
    calls = [outcome(r, *hist.get(r["ticker"], ([], []))) for r in runs]

    judged = [c for c in calls if c["verdict"] in ("right", "wrong")]
    by_rec = {}
    for rec in ("BUY", "HOLD", "SELL"):
        group = [c for c in judged if c["recommendation"] == rec]
        if group:
            by_rec[rec] = {"calls": len(group), "right": sum(c["verdict"] == "right" for c in group),
                           "avg4w": round(sum(c["after4w"] for c in group) / len(group), 2)}
    summary = {"calls": len(calls), "judged": len(judged),
               "right": sum(c["verdict"] == "right" for c in judged),
               "tooEarly": sum(c["verdict"] == "too early" for c in calls), "byRecommendation": by_rec,
               "rule": f"A call is judged four weeks ({MONTH} trading days) later. BUY is borne out if "
                       f"the price rose, SELL if it fell, HOLD if it stayed within {HOLD_BAND:.0f}%."}
    return {"calls": calls, "summary": summary}
