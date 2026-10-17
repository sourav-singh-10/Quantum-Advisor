"""Optional, free phone notifications through a Telegram bot.

Setup: create a bot with @BotFather, then set TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_NAME.
Linking: the app gives the user a one-time code inside a t.me/<bot>?start=<code> link; when
they press Start, the bot receives "/start <code>". ``poll_updates`` reads new messages
(no webhook needed, so it works on a free server) and links the chat to the account.
"""
from __future__ import annotations

import logging
import secrets

import requests

import config

log = logging.getLogger("quantum-advisor.telegram")
API = "https://api.telegram.org/bot{token}/{method}"


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_BOT_NAME)


def _call(method: str, **params) -> dict | None:
    if not config.TELEGRAM_BOT_TOKEN:
        return None
    try:
        r = requests.post(API.format(token=config.TELEGRAM_BOT_TOKEN, method=method),
                          json=params, timeout=config.HTTP_TIMEOUT_SECONDS)
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("telegram %s failed: %s", method, type(exc).__name__)
        return None
    if not data.get("ok"):
        log.warning("telegram %s refused: %s", method, data.get("description"))
        return None
    return data


def new_link(store, user: str) -> dict:
    code = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
    store.new_telegram_code(user, code)
    return {"code": code, "url": f"https://t.me/{config.TELEGRAM_BOT_NAME}?start={code}"}


def poll_updates(store) -> int:
    """Link chats that sent '/start <code>'. Returns how many were linked."""
    if not enabled():
        return 0
    offset = int(store.last_job("telegram_offset") or 0)
    data = _call("getUpdates", offset=offset, timeout=0, allowed_updates=["message"])
    if not data:
        return 0
    linked = 0
    for upd in data.get("result", []):
        offset = max(offset, upd["update_id"] + 1)
        msg = upd.get("message") or {}
        text, chat = (msg.get("text") or "").strip(), (msg.get("chat") or {}).get("id")
        if not chat or not text.startswith("/start"):
            continue
        parts = text.split(maxsplit=1)
        user = store.user_for_code(parts[1]) if len(parts) == 2 else None
        if user:
            store.link_telegram(user, str(chat))
            send(str(chat), "Connected to Quantum Advisor. Your 8:30 and 3:15 briefs and your alerts "
                            "will arrive here. Educational analysis, not investment advice.")
            linked += 1
        else:
            send(str(chat), "This link has expired. Open Quantum Advisor, go to Profile & goals and "
                            "press 'Connect Telegram' again.")
    store.mark_job("telegram_offset", str(offset))
    return linked


def send(chat_id: str, text: str) -> bool:
    return _call("sendMessage", chat_id=chat_id, text=text[:4000], disable_web_page_preview=True) is not None


def brief_text(brief: dict) -> str:
    s = brief.get("summary") or {}
    title = "Morning brief" if brief.get("kind") == "morning" else "Closing brief"
    lines = [f"{title}: {s.get('headline', '')}", ""]
    lines += [f"- {p}" for p in s.get("points", [])]
    if s.get("actions"):
        lines += ["", "To check:"] + [f"- {a}" for a in s["actions"]]
    t = brief.get("totals")
    if t:
        lines += ["", f"Holdings today: {'+' if t['dayPnL'] >= 0 else '-'}Rs {abs(t['dayPnL']):,.0f} "
                      f"({t['dayPnLPct']:+.2f}%)"]
    if config.APP_URL:
        lines += ["", config.APP_URL.rstrip("/") + "/app#watchlist"]
    return "\n".join(lines)


def alert_text(alert: dict) -> str:
    return f"{alert['ticker']}: {alert['title']}" + (f"\n{alert['link']}" if alert.get("link") else "")
