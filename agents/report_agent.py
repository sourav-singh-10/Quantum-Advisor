"""Report agent: writes the final plain-language report, including the agents' debate."""
from __future__ import annotations

from agents.base import BaseAgent
from core.schemas import Report


class ReportAgent(BaseAgent):
    name = "ReportAgent"
    system = ("You write short, honest investment reports for retail investors. Explain the "
              "recommendation, the main evidence, where the agents disagreed and how it was "
              "resolved, and what data was missing. No hype, no guarantees. Educational only.")

    def run(self, ctx, state: dict) -> dict:
        m, r, f, n = state["market"], state["risk"], state.get("fundamentals") or {}, \
            state.get("news") or {}
        s, debate = state["final"], state["debate"]
        disagreement = "; ".join(
            f"round {d['round']}: Risk {d['critique']['verdict']}"
            + (f" ({', '.join(o['text'] for o in d['critique']['objections'])})"
               if d["critique"]["objections"] else "")
            for d in debate)
        asked = "; ".join(f"{f['from']} asked {f['agent']}: {f['question']} -> {f['answer']}"
                          for f in state.get("followups") or [])
        if asked:
            disagreement += f". Evidence asked for: {asked}"

        def fallback():
            body = (f"{m['ticker']} trades at {m['priceDisplay']} in a {m["trend"].lower()} "
                    f"(RSI {m['rsi']}, volatility {m['volatility']}%). Risk is {r['riskLevel']} "
                    f"({r['riskScore']}). Fundamentals: {f.get('financialHealth', 'not analysed')}. "
                    f"News: {n.get('newsSentiment', 'not analysed')}. Committee: {disagreement}. "
                    f"Final call: {s['recommendation']} with {s['confidence'].lower()} confidence."
                    + (f" Agents running on rules only: {', '.join(sorted(ctx.degraded))}."
                       if ctx.degraded else ""))
            return Report(headline=f"{m['ticker']}: {s['recommendation']}", body=body)

        prompt = (f"Write the report.\nMarket: {m.get('marketSummary')} (price {m['priceDisplay']})"
                  f"\nFundamentals: {f.get('fundamentalsSummary', 'not analysed')}\nNews: "
                  f"{n.get('newsSummary', 'not analysed')}\nRisk: {r['riskSummary']}\n"
                  f"Debate: {disagreement}\nFinal: {s['recommendation']} ({s['confidence']}), "
                  f"how decided: {s['decidedBy']}. Rationale {s['rationale']}\nPortfolio advice: "
                  f"{state['portfolio']['portfolioAdvice']}\nMissing data / degraded agents: "
                  f"{sorted(ctx.failed | ctx.degraded) or 'none'}\nPrevious run: "
                  f"{state.get('lastRun') or 'none'}")
        report, meta = self.decide(ctx, prompt, Report, fallback)
        return {"aiReport": f"{report.headline}\n\n{report.body}", "reportHeadline": report.headline,
                "_llm": meta}
