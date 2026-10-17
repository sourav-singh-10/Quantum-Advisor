"""Portfolio review agent: reviews an uploaded portfolio valued at live prices."""
from __future__ import annotations

from agents.base import BaseAgent
from core.schemas import HoldingCall, PortfolioReview

RULE_ACTION = {"SELL": "TRIM", "REVIEW": "REVIEW", "BUY": "ADD", "HOLD": "HOLD"}


class PortfolioReviewAgent(BaseAgent):
    name = "PortfolioReviewAgent"
    system = ("You review the stock portfolio of a retail investor in India. Judge concentration, "
              "sector balance, volatility and valuation using only the numbers given. Recommend "
              "ADD, HOLD, TRIM or REVIEW for each holding with a one-line reason. Never recommend "
              "ADD for a holding whose live price is unavailable.")

    def run(self, ctx, analysis: dict) -> dict:
        stocks, total = analysis["stocks"], analysis["totalValue"] or 1

        top = max(stocks, key=lambda s: s["currentValue"])

        def fallback():
            notes = {r["ticker"]: r["note"] for r in analysis["recommendations"]}
            return PortfolioReview(
                summary=f"{len(stocks)} holdings across {len(analysis['sectorAllocation'])} sectors; "
                        f"the largest is {top['ticker']} at {top['currentValue'] / total * 100:.0f}% of the value.",
                actions=analysis["advice"][:5],
                holdings=[HoldingCall(ticker=s["ticker"], action=RULE_ACTION.get(s["recommendation"], "HOLD"),
                                      reason=notes.get(s["ticker"], "")) for s in stocks])

        lines = "\n".join(
            f"- {s['ticker']}: weight {s['currentValue'] / total * 100:.1f}%, P&L {s['pnlPct']:+.1f}%, "
            f"daily vol {s['volatility'] if s['volatility'] is not None else 'n/a'}%, "
            f"P/E {s['pe'] or 'n/a'}, trend {s.get('trend') or 'n/a'}, RSI {s.get('rsi') or 'n/a'}, "
            f"sector {s['sector']}, price {s['priceSource']}, rule call {s['recommendation']} "
            f"({s.get('reason', '')})"
            for s in stocks)
        prompt = (f"Portfolio value INR {analysis['totalValue']:,.0f}, invested INR "
                  f"{analysis['totalCost']:,.0f}, P&L {analysis['totalPnLPct']:+.1f}%.\n"
                  f"Rule scores: risk {analysis['riskScore']}/100, diversification "
                  f"{analysis['diversificationScore']}/100. Sectors: {analysis['sectorAllocation']}.\n"
                  f"Holdings:\n{lines}\nWrite the review.")
        review, meta = self.decide(ctx, prompt, PortfolioReview, fallback)

        # Guardrail: no ADD without a live price; every holding gets exactly one call.
        unpriced = {s["ticker"] for s in stocks if not s["priceSource"].startswith("live")}
        calls = {h.ticker.upper(): h for h in review.holdings}
        holdings = []
        for s in stocks:
            h = calls.get(s["ticker"]) or HoldingCall(ticker=s["ticker"], action="HOLD",
                                                       reason="No specific call from the review.")
            if s["ticker"] in unpriced and h.action == "ADD":
                h = HoldingCall(ticker=s["ticker"], action="REVIEW",
                                reason="No live price available; check before adding.")
            holdings.append(h.model_dump())
        ctx.emit(self.name, "User", "result",
                 {"summary": review.summary, "actions": review.actions}, llm=meta)
        return {"summary": review.summary, "actions": review.actions, "holdings": holdings,
                "degraded": not meta.get("ok", False)}
