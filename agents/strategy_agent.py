"""Strategy agent: proposes BUY/HOLD/SELL and must answer each of Risk's objections."""
from __future__ import annotations

from agents.base import BaseAgent
from core.schemas import ObjectionResponse, StrategyDraft
from tools.position import price_targets

ORDER = ["SELL", "HOLD", "BUY"]
RANK = {"Low": 0, "Moderate": 1, "High": 2}
from tools.actions import FIT_LIMIT   # suitability gap above which a good stock is still not for this investor


def baseline(stock_score: float, fit_gap: int, trend: str) -> str:
    """The rule-based call from the same facts: the stock's own outlook, then the investor's fit.

    A stock that is fine but too risky for this investor is a HOLD (no new money), never a SELL:
    SELL is reserved for a stock whose own outlook is weak.
    """
    rec = "BUY" if stock_score < 20 else "HOLD" if stock_score < 40 else "SELL"
    if rec == "BUY" and (fit_gap > FIT_LIMIT or trend == "Downtrend"):
        rec = "HOLD"
    return rec


class StrategyAgent(BaseAgent):
    name = "StrategyAgent"
    use_reasoning_model = True
    system = ("You are the investment strategist. Recommend BUY, HOLD or SELL for this specific "
              "investor using only the analysts' numbers. BUY: put new money in. HOLD: no new money "
              "now (keep it if already owned). SELL: the stock's own outlook is weak, so an owner "
              "should exit. A sound stock that is too risky for this investor is a HOLD, not a SELL. "
              "Start from the rule baseline you are given and depart from it only for a specific "
              "fact, which you name in the rationale. When the risk manager objects, either change "
              "your recommendation or defend it with evidence; answer every objection by its id. "
              "Conceding an objection means moving towards HOLD, not past it. Never claim more "
              "confidence than the data supports.")

    def _rule_score(self, state: dict) -> float:
        """The stock's own score: risk adjusted for news and fundamentals (lower is better).

        It does not depend on the investor or on how long the debate has run, so arguing longer
        cannot by itself push the call towards SELL.
        """
        risk, news = state["risk"], state.get("news") or {}
        fund = state.get("fundamentals") or {}
        effective = risk["riskScore"] - news.get("sentimentScore", 0) * 8
        if fund.get("healthScore") is not None:
            effective -= (fund["healthScore"] - 50) / 10
        return max(5.0, min(100.0, effective))

    def propose(self, ctx, state: dict, round_: int, critique: dict | None,
                previous: dict | None) -> dict:
        cap = state.get("confidenceCap", "High")
        effective = self._rule_score(state)
        gap = state["risk"]["suitabilityGap"]
        base = baseline(effective, gap, state["market"]["trend"])

        def fallback():
            rec = base       # rules never buy into a falling price or beyond the investor's fit
            if rec == "BUY" and critique and critique["verdict"] != "approve":
                rec = "HOLD"   # concede the objection by moving towards HOLD
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
                                            f"Rule-based stock score {effective:.0f} (risk adjusted for news and fundamentals); "
                                            f"fit gap {gap:+d}"])

        m, f, n, p, r = (state["market"], state.get("fundamentals") or {}, state.get("news") or {},
                         state["profile"], state["risk"])
        prompt = (
            f"Round {round_}. Stock {m['ticker']} at {m['priceDisplay']}.\n"
            f"Market: trend {m['trend']}, RSI {m['rsi']}, volatility {m['volatility']}%, 1-month "
            f"change {m['change1mPct']}%. {m.get('marketSummary', '')}\n"
            f"Fundamentals: {f.get('fundamentalsSummary', 'not analysed')} "
            f"(health {f.get('financialHealth', 'Unknown')})\n"
            f"News: {n.get('newsSentiment', 'not analysed')} - {n.get('newsSummary', '')}\n"
            f"Company document: {(state.get('document') or {}).get('documentSummary', 'none attached')}\n"
            f"Risk: score {r['riskScore']} ({r['riskLevel']}), suitability gap "
            f"{r['suitabilityGap']:+d}, {r['riskSummary']}\n"
            f"Investor: {p['profileSummary']} Constraints: {p['constraints']}\n"
            f"Planner's focus: {state.get('focus', '')}. Max confidence allowed: {cap}.\n"
            f"Rule baseline: {base}. Stock score {effective:.0f} (<20 suggests BUY, <40 HOLD, else "
            f"SELL), then a BUY becomes HOLD when the suitability gap is above {FIT_LIMIT} or the "
            f"trend is down. The stock score is NOT the risk score: it is risk {r['riskScore']} "
            f"adjusted for news and fundamentals. Quote the risk score as {r['riskScore']}.\n"
            + "".join(f"Evidence gathered on request ({f['agent']}): Q: {f['question']} A: {f['answer']}"
                      f"{' (this changes the earlier view)' if f.get('changesView') else ''}\n"
                      for f in state.get("followups") or [])
            + (f"Your previous draft: {previous}\nRisk manager's critique: {critique}\n"
               "Answer each objection by id." if critique else "This is your first draft.")
            + ("\nIf one specific piece of evidence from an analyst could change your call, you may "
               "put it in 'followup' instead of guessing; otherwise leave it empty."
               if state.get("followupsLeft", 0) > 0 and not critique else ""))
        draft, meta = self.decide(ctx, prompt, StrategyDraft, fallback)
        if draft.followup and (state.get("followupsLeft", 0) <= 0 or critique
                               or draft.followup.agent not in state.get("availableAnalysts", [])):
            draft.followup = None
        if RANK[draft.confidence] > RANK[cap]:
            draft.confidence = cap
        targets = price_targets(m["currentPrice"], m["volatility"], draft.recommendation)
        out = {**draft.model_dump(), **targets,
               "buyScore": round(max(0, min(100, 100 - effective * 2))),
               "effectiveRisk": round(effective, 1), "baseline": base}
        ctx.emit(self.name, "RiskManager", "draft",
                 {k: out[k] for k in ("recommendation", "confidence", "rationale", "responses")
                  if k in out} | ({"followup": out["followup"]} if out.get("followup") else {}),
                 round_=round_, llm=meta)
        return out
