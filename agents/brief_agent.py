"""Market watch agent: turns the day's numbers and headlines for a watchlist or a set of
holdings into a short brief. The numbers come from tools; the agent only chooses what
matters and says it plainly. Without an LLM it falls back to the rule-based flags."""
from __future__ import annotations

from agents.base import BaseAgent
from core.schemas import BriefSummary
from tools.safety import untrusted


def _fmt(v, suffix="%", signed=True):
    if v is None:
        return "n/a"
    return f"{v:+.1f}{suffix}" if signed else f"{v:.1f}{suffix}"


class BriefAgent(BaseAgent):
    name = "BriefAgent"
    system = ("You write a short market brief for a retail investor in India. Use only the "
              "numbers and headlines given. Lead with what changed or what needs attention. "
              "Refer to each stock by its NSE symbol (e.g. TCS), in every point. Do not tell the reader to buy or sell; suggest "
              "what to check instead. Plain words, no jargon, no hype.")

    def summarise(self, ctx, kind: str, items: list[dict], rule_summary: dict, extra: str = "") -> dict:
        def fallback():
            return BriefSummary(headline=rule_summary["headline"], points=rule_summary["points"][:4],
                                actions=rule_summary.get("actions", [])[:3])

        lines = []
        for it in items:
            if it.get("error"):
                lines.append(f"- {it['ticker']}: no price data ({it['error']})")
                continue
            news = untrusted("; ".join(f"[{n['tone']}{', material' if n['material'] else ''}] {n['title']}"
                                       for n in it.get("news", [])[:3]), "headlines") \
                if it.get("news") else "no recent headlines"
            held = ""
            if it.get("quantity"):
                held = (f", held {it['quantity']:g} @ {it['buyPrice']:,.2f} "
                        f"(P&L {_fmt(it.get('pnlPct'))}, today {it.get('dayPnL', 0):+,.0f} INR, "
                        f"weight {_fmt(it.get('weight'), signed=False)})")
            lines.append(
                f"- {it['ticker']} ({it.get('name') or ''}): price {it['price']:,.2f}, day {_fmt(it['changePct'])}, "
                f"5d {_fmt(it.get('change5dPct'))}, 1m {_fmt(it.get('change1mPct'))}, "
                f"{it['rangeLabel']} range {it['low52']:,.0f}-{it['high52']:,.0f}, trend {it['trend']}, "
                f"RSI {it['rsi']}, volume x{it.get('volumeRatio') or 'n/a'} of normal{held}. "
                f"Flags: {', '.join(f['text'] for f in it.get('flags', [])) or 'none'}. News: {news}")
        when = "before the market opens (8:30 AM)" if kind == "morning" else "15 minutes before the close (3:15 PM)"
        prompt = (f"Write the brief to read {when}.\n{extra}\nStocks:\n" + "\n".join(lines))
        out, meta = self.decide(ctx, prompt, BriefSummary, fallback)
        ctx.emit(self.name, "User", "result", {"headline": out.headline, "points": out.points}, llm=meta)
        return {**out.model_dump(), "byLLM": bool(meta.get("ok"))}
