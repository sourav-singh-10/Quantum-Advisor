"""Market analyst: chooses price sources itself, computes indicators, interprets them."""
from __future__ import annotations

from agents.base import BaseAgent, Tool
from core.schemas import MarketView
from tools.base import ToolError
from tools.indicators import compute_indicators
from tools.market_data import SOURCES, chart_series, get_price_history, volume_signal


class MarketAnalyst(BaseAgent):
    name = "MarketAnalyst"
    system = ("You are a market analyst for NSE stocks. Get at least 20 daily closing prices "
              "from one source. Sources are free but rate-limited: yfinance has no fixed quota, "
              "alphavantage allows 25 calls a day, marketstack only 100 a month, so prefer them "
              "in that order unless an observation says otherwise. If a source fails, try "
              "another; never call the same failing source twice.")

    def run(self, ctx, ticker: str, instruction: str = "") -> dict:
        def fetch(arg: str):
            # "yfinance" or "yfinance:HDFCBANK" (another NSE symbol, e.g. after a merger)
            src, _, sym = (arg or "").replace(" ", ":", 1).partition(":")
            sym = (sym or ticker).strip().upper().removesuffix(".NS").removesuffix(".BO")
            return {"symbol": sym, "prices": get_price_history(sym, src)}

        tool = Tool(
            name="get_price_history",
            description=(f"daily closes for {ticker}; argument = a source ({', '.join(SOURCES)}), "
                         "optionally followed by ':SYMBOL' to use a different NSE symbol, e.g. "
                         "'yfinance:HDFCBANK' when told the company now trades under another name"),
            run=fetch,
            summarize=lambda r: f"{r['symbol']}: {len(r['prices'])} prices, last close "
                                f"{r['prices'][-1]:.2f}",
        )
        default = [(tool.name, s) for s in SOURCES]
        done = lambda obs: any(o["ok"] for o in obs)
        goal = f"Fetch price history for {ticker}. {instruction}".strip()
        observations = self.tool_loop(ctx, goal, [tool], default, done)

        success = next((o for o in observations if o["ok"]), None)
        if not success:
            errors = "; ".join(f"{o['argument']}: {o['error']}" for o in observations)
            raise ToolError(f"no price source worked ({errors})")
        symbol = success["result"]["symbol"]
        success = {**success, "argument": success["argument"].split(":")[0],
                   "result": success["result"]["prices"]}

        ind = compute_indicators(success["result"])
        ctx.emit(self.name, "tool:compute_indicators", "tool_call",
                 {"argument": f"{len(success['result'])} prices"})
        ctx.emit("tool:compute_indicators", self.name, "tool_result", {"ok": True, **ind})
        try:
            ctx.emit(self.name, "tool:volume_signal", "tool_call", {"argument": symbol})
            ind.update(volume_signal(symbol))
            ctx.emit("tool:volume_signal", self.name, "tool_result",
                     {"ok": True, "volumeRatio": ind["volumeRatio"], "volumeLevel": ind["volumeLevel"]})
        except ToolError as exc:
            ctx.emit("tool:volume_signal", self.name, "tool_result", {"ok": False, "error": str(exc)})

        def fallback():
            mom = {"Uptrend": "Up", "Downtrend": "Down"}.get(ind["trend"], "Flat")
            extra = []
            if ind.get("macdState"):
                extra.append(f"MACD {ind['macdState'].lower()}")
            if ind.get("bbState"):
                extra.append(f"price {ind['bbState'].lower()}")
            return MarketView(
                summary=f"{ind['trend']} with RSI {ind['rsi']:.0f} and "
                        f"{ind['volatility']:.1f}% daily volatility; "
                        f"{abs(ind['belowHighPct']):.0f}% below its six-month high"
                        + (f"; {', '.join(extra)}" if extra else "")
                        + (f", {ind['volumeLevel'].lower()} trading volume "
                           f"({ind['volumeRatio']}x the 50-day average)." if "volumeRatio" in ind
                           else "."),
                momentum=mom,
                data_quality="Good" if ind["observations"] >= 50 else "Limited")

        prompt = (f"Indicators for {symbol} (computed, do not change them): {ind}. "
                  f"Source: {success['argument']}. Interpret them together for an investor.")
        view, meta = self.decide(ctx, prompt, MarketView, fallback)
        return {
            "ticker": symbol,
            "symbolUsed": symbol,
            **ind,
            "priceDisplay": f"₹{ind['currentPrice']:,.2f}",
            "priceSource": success["argument"],
            "sourcesTried": [o["argument"] for o in observations],
            # last ~6 months of closes, oldest first, for the price chart in the UI
            "priceHistory": [round(x, 2) for x in success["result"][-120:]],
            **(chart_series(symbol, len(success["result"][-120:]))
               if success["argument"] == "yfinance" else {}),
            "marketSummary": view.summary,
            "momentum": view.momentum,
            "dataQuality": view.data_quality,
            "_llm": meta,
        }

    # ------------------------------------------------------------ follow-up questions
    def followup_facts(self, ctx, ticker: str, question: str, previous: dict):
        """A longer look than the analysis window: one year of closes from yfinance."""
        from tools.indicators import long_view
        from tools.market_snapshot import _yf_year
        symbol = previous.get("symbolUsed") or ticker
        facts = [f"Current price {previous.get('currentPrice')}, trend {previous.get('trend')}, "
                 f"RSI {previous.get('rsi')}, 1-month change {previous.get('change1mPct')}%"]
        for k, label in (("macdState", "MACD"), ("bbState", "Bollinger"), ("change3mPct", "3-month change %"),
                         ("support", "60-day support"), ("resistance", "60-day resistance")):
            if previous.get(k) is not None:
                facts.append(f"{label}: {previous[k]}")
        year = self.use_tool(ctx, "get_long_history", f"{symbol} 1y",
                             lambda: long_view(_yf_year(symbol)[0]),
                             lambda v: f"{v['sessions']} sessions, 1-year change {v['change1yPct']}%")
        if year:
            facts.append(f"Over {year['sessions']} sessions: change {year['change1yPct']}%, range "
                         f"{year['low']}-{year['high']}, {year['fromHighPct']}% from the high, worst "
                         f"fall {year['maxDrawdownPct']}%"
                         + (f", {'above' if year['above200dma'] else 'below'} the 200-day average "
                            f"{year['ma200']}" if "ma200" in year else ""))
            rule = (f"Over the last year the stock is {year['change1yPct']:+.1f}% and "
                    f"{abs(year['fromHighPct']):.0f}% below its high, with a worst fall of "
                    f"{abs(year['maxDrawdownPct']):.0f}%"
                    + ("; it trades above its 200-day average." if year.get("above200dma")
                       else "; it trades below its 200-day average." if "ma200" in year else "."))
        else:
            rule = "A one-year history was not available; only the analysis window can be used."
        return facts, rule
