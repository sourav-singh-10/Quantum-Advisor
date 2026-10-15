"""Fundamentals analyst: real ratios from yfinance, rule score, LLM interpretation."""
from __future__ import annotations

from agents.base import BaseAgent
from core.schemas import FundamentalsView
from tools.base import ToolError
from tools import fundamentals_data
from tools.fundamentals_data import score_fundamentals


class FundamentalsAnalyst(BaseAgent):
    name = "FundamentalsAnalyst"
    system = ("You are an equity fundamentals analyst. Judge valuation, profitability and "
              "leverage relative to the company's sector. Say clearly when data is missing.")

    def run(self, ctx, ticker: str, instruction: str = "") -> dict:
        ctx.emit(self.name, "tool:get_fundamentals", "tool_call", {"argument": ticker})
        try:
            data = fundamentals_data.fetch_fundamentals(ticker)
            ctx.emit("tool:get_fundamentals", self.name, "tool_result", {"ok": True, **data})
        except ToolError as exc:
            ctx.emit("tool:get_fundamentals", self.name, "tool_result",
                     {"ok": False, "error": str(exc)})
            return {"pe": None, "roe": None, "de": None, "financialHealth": "Unknown",
                    "healthScore": None, "fundamentalsSummary": f"Unavailable: {exc}",
                    "fundamentalsPoints": [], "fundamentalsAvailable": False}

        rules = score_fundamentals(data)

        def fallback():
            return FundamentalsView(
                summary=f"Rule score {rules['healthScore']}/100: "
                        + (", ".join(rules["notes"]) or "no strong signals"),
                financialHealth=rules["financialHealth"], key_points=rules["notes"])

        prompt = (f"Fundamentals for {ticker} ({data.get('name')}, sector {data.get('sector')}): "
                  f"PE {data['pe']}, ROE {data['roe']}%, debt/equity {data['de']}, "
                  f"profit margin {data['profitMargin']}%, market cap INR {data['marketCapCr']} cr. "
                  f"Rule-based score {rules['healthScore']}/100 ({', '.join(rules['notes'])}); "
                  f"missing: {rules['missing']}. Focus: {instruction or 'overall health'}.")
        view, meta = self.decide(ctx, prompt, FundamentalsView, fallback)
        return {**{k: data[k] for k in ("pe", "roe", "de", "profitMargin", "sector")},
                "healthScore": rules["healthScore"], "financialHealth": view.financialHealth,
                "fundamentalsSummary": view.summary, "fundamentalsPoints": view.key_points,
                "fundamentalsAvailable": True, "_llm": meta}
