"""Market analyst: chooses price sources itself, computes indicators, interprets them."""
from __future__ import annotations

from agents.base import BaseAgent, Tool
from core.schemas import MarketView
from tools.base import ToolError
from tools.indicators import compute_indicators
from tools.market_data import SOURCES, get_price_history


class MarketAnalyst(BaseAgent):
    name = "MarketAnalyst"
    system = ("You are a market analyst for NSE stocks. Get at least 20 daily closing prices "
              "from one source. Sources are free but rate-limited: yfinance has no fixed quota, "
              "alphavantage allows 25 calls a day, marketstack only 100 a month, so prefer them "
              "in that order unless an observation says otherwise. If a source fails, try "
              "another; never call the same failing source twice.")

    def run(self, ctx, ticker: str, instruction: str = "") -> dict:
        tool = Tool(
            name="get_price_history",
            description=f"daily closes for {ticker}; argument = one of {', '.join(SOURCES)}",
            run=lambda src: get_price_history(ticker, src),
            summarize=lambda p: f"{len(p)} prices, last close {p[-1]:.2f}",
        )
        default = [(tool.name, s) for s in SOURCES]
        done = lambda obs: any(o["ok"] for o in obs)
        goal = f"Fetch price history for {ticker}. {instruction}".strip()
        observations = self.tool_loop(ctx, goal, [tool], default, done)

        success = next((o for o in observations if o["ok"]), None)
        if not success:
            errors = "; ".join(f"{o['argument']}: {o['error']}" for o in observations)
            raise ToolError(f"no price source worked ({errors})")

        ind = compute_indicators(success["result"])
        ctx.emit(self.name, "tool:compute_indicators", "tool_call",
                 {"argument": f"{len(success['result'])} prices"})
        ctx.emit("tool:compute_indicators", self.name, "tool_result", {"ok": True, **ind})

        def fallback():
            mom = {"Uptrend": "Up", "Downtrend": "Down"}.get(ind["trend"], "Flat")
            return MarketView(
                summary=f"{ind['trend']} with RSI {ind['rsi']:.0f} and "
                        f"{ind['volatility']:.1f}% daily volatility.",
                momentum=mom,
                data_quality="Good" if ind["observations"] >= 50 else "Limited")

        prompt = (f"Indicators for {ticker} (computed, do not change them): {ind}. "
                  f"Source: {success['argument']}. Interpret them together for an investor.")
        view, meta = self.decide(ctx, prompt, MarketView, fallback)
        return {
            "ticker": ticker,
            **ind,
            "priceDisplay": f"₹{ind['currentPrice']:,.2f}",
            "priceSource": success["argument"],
            "sourcesTried": [o["argument"] for o in observations],
            "marketSummary": view.summary,
            "momentum": view.momentum,
            "dataQuality": view.data_quality,
            "_llm": meta,
        }
