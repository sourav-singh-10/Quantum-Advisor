"""Strategy agent: proposes BUY/HOLD/SELL and must answer each of Risk's objections."""
from __future__ import annotations

from agents.base import BaseAgent
from core.schemas import ObjectionResponse, StrategyDraft
from tools.position import price_targets

ORDER = ["SELL", "HOLD", "BUY"]
RANK = {"Low": 0, "Moderate": 1, "High": 2}


class StrategyAgent(BaseAgent):
    name = "StrategyAgent"
    use_reasoning_model = True
    system = ("You are the investment strategist. Recommend BUY, HOLD or SELL for this specific "
              "investor using only the analysts' numbers. When the risk manager objects, either "
              "change your recommendation or defend it with evidence; answer every objection by "
              "its id. Never claim more confidence than the data supports.")

    def _rule_score(self, state: dict, revisions: int) -> float:
        risk, news = state["risk"], state.get("news") or {}
        fund = state.get("fundamentals") or {}
        effective = risk["riskScore"] - news.get("sentimentScore", 0) * 8
        if fund.get("healthScore") is not None:
            effective -= (fund["healthScore"] - 50) / 10
        effective += 8 * revisions + max(0, risk["suitabilityGap"]) / 2
        return max(5.0, min(100.0, effective))

    def propose(self, ctx, state: dict, round_: int, critique: dict | None,
                previous: dict | None) -> dict:
        cap = state.get("confidenceCap", "High")
        effective = self._rule_score(state, revisions=round_ - 1)

        def fallback():
            rec = "BUY" if effective < 20 else "HOLD" if effective < 40 else "SELL"
            if critique and critique["verdict"] == "veto" and rec == "BUY":
                rec = "HOLD"
            conf = "Moderate" if RANK["Moderate"] <= RANK[cap] else cap
            responses = [ObjectionResponse(objection_id=o["id"],
                                           response=f"Accepted; recommendation now {rec}.")
                         for o in (critique or {}).get("objections", [])]
            m = state["market"]
            return StrategyDraft(recommendation=rec, confidence=conf, responses=responses,
                                 rationale=[f"Trend {m['trend']}, RSI {m['rsi']}",
                                            f"Risk score {state['risk']['riskScore']} "
                                            f"({state['risk']['riskLevel']})",
                                            f"News {state.get('news', {}).get('newsSentiment', 'n/a')}",
                                            f"Rule-based effective risk {effective:.0f}"])

        m, f, n, p, r = (state["market"], state.get("fundamentals") or {}, state.get("news") or {},
                         state["profile"], state["risk"])
        prompt = (
            f"Round {round_}. Stock {m['ticker']} at {m['priceDisplay']}.\n"
            f"Market: trend {m['trend']}, RSI {m['rsi']}, volatility {m['volatility']}%, 1-month "
            f"change {m['change1mPct']}%. {m.get('marketSummary', '')}\n"
            f"Fundamentals: {f.get('fundamentalsSummary', 'not analysed')} "
            f"(health {f.get('financialHealth', 'Unknown')})\n"
            f"News: {n.get('newsSentiment', 'not analysed')} - {n.get('newsSummary', '')}\n"
            f"Risk: score {r['riskScore']} ({r['riskLevel']}), suitability gap "
            f"{r['suitabilityGap']:+d}, {r['riskSummary']}\n"
            f"Investor: {p['profileSummary']} Constraints: {p['constraints']}\n"
            f"Planner's focus: {state.get('focus', '')}. Max confidence allowed: {cap}.\n"
            f"Rule-based reference: effective risk {effective:.0f} (<20 suggests BUY, "
            f"<40 HOLD, else SELL).\n"
            + (f"Your previous draft: {previous}\nRisk manager's critique: {critique}\n"
               "Answer each objection by id." if critique else "This is your first draft."))
        draft, meta = self.decide(ctx, prompt, StrategyDraft, fallback)
        if RANK[draft.confidence] > RANK[cap]:
            draft.confidence = cap
        targets = price_targets(m["currentPrice"], m["volatility"], draft.recommendation)
        out = {**draft.model_dump(), **targets,
               "buyScore": round(max(0, min(100, 100 - effective * 2))),
               "effectiveRisk": round(effective, 1)}
        ctx.emit(self.name, "RiskManager", "draft",
                 {k: out[k] for k in ("recommendation", "confidence", "rationale", "responses")},
                 round_=round_, llm=meta)
        return out
