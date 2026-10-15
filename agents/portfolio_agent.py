"""Portfolio agent: sizes the position for this investor and turns it into concrete advice."""
from __future__ import annotations

import math

from agents.base import BaseAgent
from core.schemas import PortfolioAdvice
from tools.position import position_size


class PortfolioAgent(BaseAgent):
    name = "PortfolioAgent"
    system = ("You turn a final recommendation and computed position size into 2-4 short, "
              "concrete action lines for a retail investor in India. Use the given numbers "
              "exactly; never suggest buying when the recommendation is HOLD or SELL.")

    def run(self, ctx, state: dict, request: dict) -> dict:
        m, p, s = state["market"], state["profile"], state["final"]
        sizing = position_size(request["portfolioValue"], m["currentPrice"], s["recommendation"],
                               p["riskCapacityScore"], p["maxPositionPct"])
        ctx.emit(self.name, "tool:position_size", "tool_call",
                 {"argument": f"{s['recommendation']}, INR {request['portfolioValue']:,.0f}"})
        ctx.emit("tool:position_size", self.name, "tool_result", {"ok": True, **sizing})

        month_move = m["volatility"] * math.sqrt(21) / 100
        low, high = m["currentPrice"] * (1 - month_move), m["currentPrice"] * (1 + month_move)
        expected = f"Typical 1-month range: ₹{low:,.0f} – ₹{high:,.0f} (±{month_move * 100:.1f}%)"

        def fallback():
            if s["recommendation"] == "BUY" and sizing["units"] > 0:
                lines = [f"Buy up to {sizing['units']} shares (about ₹{sizing['amount']:,.0f}, "
                         f"{sizing['positionPct']}% of your portfolio).",
                         f"Place a stop-loss near ₹{s['stopLoss']:,.2f}."]
            elif s["recommendation"] == "BUY":
                lines = ["Recommendation is BUY, but one share costs more than your position "
                         "limit allows; consider a smaller-priced alternative."]
            elif s["recommendation"] == "HOLD":
                lines = ["Do not add new money now. If you already hold it, keep your position.",
                         f"Re-check if the price moves outside ₹{low:,.0f} – ₹{high:,.0f}."]
            else:
                lines = ["Avoid new purchases. If you hold it, consider reducing your position.",
                         f"Watch ₹{s['stopLoss']:,.2f} as the level where the downside view fails."]
            return PortfolioAdvice(advice=lines)

        prompt = (f"Final recommendation {s['recommendation']} ({s['confidence']}) for "
                  f"{m['ticker']} at {m['priceDisplay']}. Sizing (computed): {sizing}. Targets "
                  f"{s['targetPrice1']} / {s['targetPrice2']}, stop-loss {s['stopLoss']}. "
                  f"{expected}. Investor: {p['profileSummary']} Constraints {p['constraints']}.")
        advice, meta = self.decide(ctx, prompt, PortfolioAdvice, fallback)
        return {"portfolioAdvice": advice.advice, "positionSizing": sizing,
                "expectedRange": expected, "_llm": meta}
