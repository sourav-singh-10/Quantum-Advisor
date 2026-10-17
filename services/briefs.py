"""Watchlist briefs and alerts.

    08:30 IST  morning brief for every watchlist: last close, overnight news, what to watch
    09:00-15:30  every 30 minutes: material headlines and moves of 3% or more become alerts
    15:15 IST  closing brief for saved holdings: today's P&L, movers, news, flags, suggestions

``run_due`` decides what is due and is called by the in-process scheduler every minute,
by /api/cron/tick (an external free cron wakes a sleeping server), and lazily when a user
opens the briefs page.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone

import config
from agents.brief_agent import BriefAgent
from core.context import RunContext
from core.tracer import Tracer
from core.watch_store import WatchStore
from services.llm_service import LLMClient
from tools import symbols
from tools.base import ToolError
from tools.market_snapshot import snapshot
from tools.news_watch import company_news
from tools.portfolio_analyzer import SECTORS

log = logging.getLogger("quantum-advisor.briefs")

IST = timezone(timedelta(hours=5, minutes=30))     # India has no daylight saving
MORNING_AT, CLOSING_AT = time(8, 30), time(15, 15)
SWEEP_FROM, SWEEP_TO = time(9, 0), time(15, 35)
SWEEP_EVERY_MIN = 25
BIG_MOVE_PCT = 3.0

_job_lock = threading.Lock()


def now_ist() -> datetime:
    return datetime.now(IST)


# ------------------------------------------------------------------ per-stock facts
def _flags(s: dict, news: list[dict]) -> list[dict]:
    f = []
    ch = s.get("changePct")
    if ch is not None and abs(ch) >= BIG_MOVE_PCT:
        f.append({"text": f"{'Up' if ch > 0 else 'Down'} {abs(ch):.1f}% on the day", "tone": "up" if ch > 0 else "down"})
    if s.get("fromHighPct") is not None and s["fromHighPct"] >= -2:
        f.append({"text": f"Near its {s['rangeLabel']} high", "tone": "up"})
    elif s.get("fromLowPct") is not None and s["fromLowPct"] <= 3:
        f.append({"text": f"Near its {s['rangeLabel']} low", "tone": "down"})
    if s.get("volumeRatio") and s["volumeRatio"] >= 2:
        f.append({"text": f"Volume {s['volumeRatio']:.1f}x normal", "tone": "watch"})
    if s.get("rsi") is not None:
        if s["rsi"] >= 70:
            f.append({"text": f"Overbought (RSI {s['rsi']:.0f})", "tone": "watch"})
        elif s["rsi"] <= 30:
            f.append({"text": f"Oversold (RSI {s['rsi']:.0f})", "tone": "watch"})
    material = [n for n in news if n["material"]]
    if material:
        tone = material[0]["tone"]
        f.append({"text": f"{len(material)} price-moving headline{'s' if len(material) > 1 else ''}",
                  "tone": "down" if tone == "Negative" else "up" if tone == "Positive" else "watch"})
    return f


def stock_facts(ticker: str, name: str | None, news_hours: float) -> dict:
    name = name or symbols.name_for(ticker)
    try:
        s = snapshot(ticker)
    except ToolError as exc:
        return {"ticker": ticker, "requested": ticker, "name": name, "error": str(exc)[:160],
                "news": [], "flags": []}
    news = company_news(s["ticker"], name, max_age_hours=news_hours)[:5]
    # "requested" is what the user saved; "ticker" may be the new symbol after a rename.
    return {**s, "requested": ticker, "name": name, "news": news, "flags": _flags(s, news)}


def _gather(pairs: list[tuple[str, str | None]], news_hours: float) -> list[dict]:
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(lambda p: stock_facts(p[0], p[1], news_hours), pairs))


# ------------------------------------------------------------------ rule summaries (no LLM)
def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def _mover_line(it: dict) -> str:
    return f"{it['ticker']} {it['changePct']:+.1f}% at ₹{it['price']:,.2f}"


def morning_rules(items: list[dict]) -> dict:
    ok = [i for i in items if not i.get("error")]
    if not ok:
        return {"headline": "No prices could be fetched for your watchlist.", "points": [], "actions": []}
    up = [i for i in ok if (i["changePct"] or 0) > 0]
    movers = sorted(ok, key=lambda i: -abs(i["changePct"] or 0))
    material = [i for i in ok if any(n["material"] for n in i["news"])]
    headline = (f"{len(up)} of {len(ok)} watchlist stocks closed higher; "
                f"the biggest move was {_mover_line(movers[0])}.")
    points = []
    for i in material[:2]:
        # a headline with a clear tone says more than a neutral one
        n = sorted((n for n in i["news"] if n["material"]), key=lambda n: n["tone"] == "Neutral")[0]
        points.append(f"{i['ticker']}: {n['title']}")
    for i in movers:
        for f in i["flags"]:
            if len(points) < 4 and "headline" not in f["text"]:
                points.append(f"{i['ticker']}: {_lower_first(f['text'])}.")
    actions = [f"Read the latest news on {i['ticker']} before the market opens." for i in material[:2]]
    return {"headline": headline, "points": points[:4], "actions": actions}


def closing_rules(items: list[dict], totals: dict) -> dict:
    ok = [i for i in items if not i.get("error")]
    if not ok:
        return {"headline": "No prices could be fetched for your holdings.", "points": [], "actions": []}
    sign = "up" if totals["dayPnL"] >= 0 else "down"
    now = now_ist()
    open_now = now.weekday() < 5 and time(9, 15) <= now.time() <= time(15, 30)
    when = (", with 15 minutes left to trade" if open_now and now.time() >= time(15, 0)
            else " so far today" if open_now else " on the last trading day")
    headline = f"Your holdings are {sign} ₹{abs(totals['dayPnL']):,.0f} ({totals['dayPnLPct']:+.2f}%){when}."
    points = [f"Biggest move: {_mover_line(max(ok, key=lambda i: abs(i['changePct'] or 0)))}."]
    points += [f"{i['ticker']}: {_lower_first(f['text'])}." for i in ok for f in i["flags"]
               if f["tone"] in ("down", "watch")][:3]
    return {"headline": headline, "points": points[:4], "actions": totals["suggestions"][:3]}


def suggestions(items: list[dict], sectors: dict) -> list[str]:
    out = []
    ok = [i for i in items if not i.get("error")]
    for i in sorted(ok, key=lambda i: i["changePct"] or 0):
        neg_news = [n for n in i["news"] if n["material"] and n["tone"] == "Negative"]
        if (i["changePct"] or 0) <= -BIG_MOVE_PCT and neg_news:
            out.append(f"{i['ticker']} is down {abs(i['changePct']):.1f}% with negative news. Read it before "
                       f"the close and decide whether it changes why you own it.")
        elif (i["changePct"] or 0) <= -BIG_MOVE_PCT:
            out.append(f"{i['ticker']} is down {abs(i['changePct']):.1f}% without clear news. Check for a "
                       f"market-wide or sector fall before reacting.")
    for i in ok:
        if i.get("pnlPct") is not None and i["pnlPct"] <= -15 and i["trend"] == "Downtrend":
            out.append(f"{i['ticker']} is {abs(i['pnlPct']):.0f}% below your buy price and still falling. "
                       f"Decide on a stop-loss level.")
        if i.get("rsi", 0) >= 75 and (i.get("fromHighPct") or -99) >= -2:
            out.append(f"{i['ticker']} is near its high and overbought (RSI {i['rsi']:.0f}). Avoid adding "
                       f"at today's price.")
        if (i.get("weight") or 0) > 25:
            out.append(f"{i['ticker']} is {i['weight']:.0f}% of your holdings. Avoid adding more to it.")
    for sector, pct in sectors.items():
        if pct > 40 and sector != "Other":
            out.append(f"{sector} is {pct:.0f}% of your holdings. New money could go to another sector.")
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------ briefs
def _summarise(user: str, kind: str, items: list[dict], rules: dict, extra: str = "") -> tuple[dict, str]:
    llm, tracer = LLMClient(), Tracer()
    ctx = RunContext(llm=llm, tracer=tracer, user_key=user)
    ctx.emit("Scheduler", BriefAgent.name, "request", {"kind": kind, "stocks": [i["ticker"] for i in items]})
    summary = BriefAgent().summarise(ctx, kind, items, rules, extra)
    ctx.emit(BriefAgent.name, "User", "final", {"status": "ok" if summary["byLLM"] else "degraded"})
    return summary, tracer.run_id


def build_morning(store: WatchStore, user: str, day: str | None = None) -> dict | None:
    watch = store.watchlist(user)
    if not watch:
        return None
    items = _gather([(w["ticker"], w["name"]) for w in watch], news_hours=20)
    summary, run_id = _summarise(user, "morning", items, morning_rules(items))
    brief = {"kind": "morning", "day": day or now_ist().date().isoformat(), "items": items,
             "summary": summary, "runId": run_id, "generatedIst": now_ist().strftime("%d %b %Y, %I:%M %p")}
    store.save_brief(user, "morning", brief["day"], brief)
    return brief


def build_closing(store: WatchStore, user: str, day: str | None = None) -> dict | None:
    held = store.holdings(user)
    if not held:
        return None
    items = _gather([(h["ticker"], None) for h in held], news_hours=10)
    by_ticker = {h["ticker"]: h for h in held}
    total_value = day_pnl = cost = 0.0
    for i in items:
        h = by_ticker.get(i["requested"], {})
        i["quantity"], i["buyPrice"] = h.get("quantity", 0), h.get("buy_price", 0)
        if i.get("error"):
            continue
        i["value"] = round(i["quantity"] * i["price"], 2)
        i["dayPnL"] = round(i["quantity"] * (i["price"] - i["prevClose"]), 2)
        i["pnlPct"] = round((i["price"] / i["buyPrice"] - 1) * 100, 2) if i["buyPrice"] else None
        i["sector"] = SECTORS.get(i["ticker"], "Other")
        total_value += i["value"]
        day_pnl += i["dayPnL"]
        cost += i["quantity"] * i["buyPrice"]
    sectors: dict[str, float] = {}
    for i in items:
        if not i.get("error") and total_value:
            i["weight"] = round(i["value"] / total_value * 100, 1)
            sectors[i["sector"]] = round(sectors.get(i["sector"], 0) + i["weight"], 1)
    prev_value = total_value - day_pnl
    totals = {"value": round(total_value, 2), "dayPnL": round(day_pnl, 2),
              "dayPnLPct": round(day_pnl / prev_value * 100, 2) if prev_value else 0.0,
              "totalPnL": round(total_value - cost, 2),
              "totalPnLPct": round((total_value / cost - 1) * 100, 2) if cost else 0.0,
              "sectors": sectors}
    totals["suggestions"] = suggestions(items, sectors)

    # Watchlist stocks that moved a lot today, as a short footnote.
    held_set = {i["requested"] for i in items}
    watch = [w for w in store.watchlist(user) if w["ticker"] not in held_set]
    watch_items = _gather([(w["ticker"], w["name"]) for w in watch], news_hours=10) if watch else []
    watch_moves = [w for w in watch_items if not w.get("error") and abs(w["changePct"] or 0) >= 2]

    extra = (f"Holdings value INR {total_value:,.0f}; today {day_pnl:+,.0f} INR ({totals['dayPnLPct']:+.2f}%); "
             f"overall P&L {totals['totalPnLPct']:+.1f}%. Sectors: {sectors}. "
             f"Rule-based things to check: {totals['suggestions'] or 'none'}.")
    summary, run_id = _summarise(user, "closing", items, closing_rules(items, totals), extra)
    brief = {"kind": "closing", "day": day or now_ist().date().isoformat(), "items": items,
             "totals": totals, "watchMoves": watch_moves, "summary": summary, "runId": run_id,
             "generatedIst": now_ist().strftime("%d %b %Y, %I:%M %p")}
    store.save_brief(user, "closing", brief["day"], brief)
    return brief


# ------------------------------------------------------------------ intraday alerts
def sweep(store: WatchStore, on_alert=None) -> int:
    """Material headlines and big moves for every watched or held stock, and the price levels
    users set. Returns the number of new alerts; ``on_alert(user, alert)`` is told about each."""
    users = store.active_users()
    who_has: dict[str, set] = {}
    names: dict[str, str | None] = {}
    for u in users:
        for w in store.watchlist(u):
            who_has.setdefault(w["ticker"], set()).add(u)
            names[w["ticker"]] = w["name"]
        for h in store.holdings(u):
            who_has.setdefault(h["ticker"], set()).add(u)
    targets = store.active_price_alerts()
    tickers = set(who_has) | {t["ticker"] for t in targets}
    if not tickers:
        return 0
    items = _gather([(t, names.get(t)) for t in tickers], news_hours=6)
    by_ticker = {it["requested"]: it for it in items}
    today, new = now_ist().date().isoformat(), 0

    def add(u, ticker, kind, dedupe, title, detail="", tone="neutral", link=""):
        nonlocal new
        if store.add_alert(u, ticker, kind, dedupe, title, detail, tone, link):
            new += 1
            if on_alert:
                on_alert(u, {"ticker": ticker, "kind": kind, "title": title, "detail": detail,
                             "tone": tone, "link": link})

    for it in items:
        owners = who_has.get(it["requested"], set())
        if it.get("error"):
            continue
        for n in it["news"]:
            if not n["material"]:
                continue
            tone = {"Positive": "up", "Negative": "down"}.get(n["tone"], "watch")
            for u in owners:
                add(u, it["ticker"], "news", f"news:{it['ticker']}:{n['title'].lower()[:120]}",
                    n["title"], n.get("source") or "", tone, n.get("link") or "")
        ch = it.get("changePct")
        if ch is not None and abs(ch) >= BIG_MOVE_PCT and it.get("asOf") in (None, today):
            band = int(abs(ch) // BIG_MOVE_PCT)
            for u in owners:
                add(u, it["ticker"], "price", f"price:{it['ticker']}:{today}:{'+' if ch > 0 else '-'}{band}",
                    f"{it['ticker']} is {'up' if ch > 0 else 'down'} {abs(ch):.1f}% today at ₹{it['price']:,.2f}",
                    f"Previous close ₹{it['prevClose']:,.2f}", "up" if ch > 0 else "down")

    for t in targets:                          # "tell me when INFY goes below 1,400"
        it = by_ticker.get(t["ticker"])
        if not it or it.get("error"):
            continue
        hit = it["price"] <= t["price"] if t["direction"] == "below" else it["price"] >= t["price"]
        if hit and store.trigger_price_alert(t["id"], it["price"]):
            word = "fallen to" if t["direction"] == "below" else "risen to"
            add(t["user_key"], it["ticker"], "target", f"target:{t['id']}",
                f"{it['ticker']} has {word} ₹{it['price']:,.2f} (your level ₹{t['price']:,.2f})",
                "Your price alert", "down" if t["direction"] == "below" else "up")
    return new


# ------------------------------------------------------------------ what is due
def _weekday(now: datetime) -> bool:
    return now.weekday() < 5


def run_due(store: WatchStore | None = None, now: datetime | None = None, notify=None,
            on_alert=None) -> list[str]:
    """Run whatever is due right now. Safe to call often and from several places."""
    if not _job_lock.acquire(blocking=False):
        return []
    try:
        store = store or WatchStore()
        now = now or now_ist()
        day, t, done = now.date().isoformat(), now.time(), []
        if not _weekday(now):
            return done
        if t >= MORNING_AT and store.last_job("morning") != day:
            store.mark_job("morning", day)
            for u in store.active_users():
                if store.brief(u, "morning", day) is None:
                    b = build_morning(store, u, day)
                    if b and notify:
                        notify(u, b)
            done.append("morning")
        if t >= CLOSING_AT and store.last_job("closing") != day:
            store.mark_job("closing", day)
            for u in store.active_users():
                if store.brief(u, "closing", day) is None:
                    b = build_closing(store, u, day)
                    if b and notify:
                        notify(u, b)
            done.append("closing")
        last = store.last_job("sweep")
        stale = not last or datetime.fromisoformat(last) <= now - timedelta(minutes=SWEEP_EVERY_MIN)
        if SWEEP_FROM <= t <= SWEEP_TO and stale:
            store.mark_job("sweep", now.isoformat(timespec="seconds"))
            sweep(store, on_alert)
            done.append("sweep")
        return done
    except Exception:
        log.exception("scheduled job failed")
        return []
    finally:
        _job_lock.release()


def due_for_user(store: WatchStore, user: str, now: datetime | None = None) -> list[str]:
    """Briefs this user should already have today but does not (the server was asleep)."""
    now = now or now_ist()
    if not _weekday(now):
        return []
    day, t, out = now.date().isoformat(), now.time(), []
    if t >= MORNING_AT and store.watchlist(user) and store.brief(user, "morning", day) is None:
        out.append("morning")
    if t >= CLOSING_AT and store.holdings(user) and store.brief(user, "closing", day) is None:
        out.append("closing")
    return out


class Scheduler:
    """Checks every minute in a daemon thread. Disabled with BRIEF_SCHEDULER=0."""

    def __init__(self, notify=None, interval: int = 60, on_alert=None, every_minute=None):
        self.notify, self.interval, self.on_alert = notify, interval, on_alert
        self.every_minute = every_minute          # e.g. read new Telegram messages
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread or not config.BRIEF_SCHEDULER:
            return
        self._thread = threading.Thread(target=self._loop, name="brief-scheduler", daemon=True)
        self._thread.start()
        log.info("brief scheduler started (8:30 morning, 3:15 closing, alerts every %s min)", SWEEP_EVERY_MIN)

    def _loop(self):
        while not self._stop.wait(self.interval):
            if self.every_minute:
                try:
                    self.every_minute()
                except Exception:
                    log.exception("minute job failed")
            run_due(notify=self.notify, on_alert=self.on_alert)

    def stop(self):
        self._stop.set()
