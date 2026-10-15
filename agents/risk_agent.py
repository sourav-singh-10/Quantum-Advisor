"""Risk manager: scores risk with rule tools, judges suitability, and critiques Strategy."""
from __future__ import annotations

from agents.base import BaseAgent
from core.schemas import Critique, Objection, RiskView
from tools.risk_rules import market_risk_score, suitability_gap

HARD_LIMIT_GAP = 15   # a BUY this far above the investor's tolerance is never approved


class RiskManager(BaseAgent):
    name = "RiskManager"
    use_reasoning_model = True
    system = ("You are the risk manager on an investment committee for retail investors. "
              "You protect the investor. Critique the strategist's draft: approve it when it "
              "is suitable, ask for a revision with specific numbered objections when it is "
              "not, and veto only a recommendation that would clearly harm this investor. "
              "Keep objection ids stable across rounds and approve once they are resolved; "
              "do not invent new objections to prolong the debate.")

    def assess(self, ctx, state: dict) -> dict:
        market, fund, news, profile = (state["market"], state.get("fundamentals") or {},
                                       state.get("news") or {}, state["profile"])
        ctx.emit(self.name, "tool:market_risk_score", "tool_call", {"argument": "market+fund+news"})
        scored = market_risk_score(market, fund, news)
        gap = suitability_gap(scored["riskScore"], profile["riskCapacityScore"])
        ctx.emit("tool:market_risk_score", self.name, "tool_result",
                 {"ok": True, **scored, "suitabilityGap": gap})

        def fallback():
            return RiskView(summary=f"{scored['riskLevel']} risk ({scored['riskScore']}); "
                                    f"suitability gap {gap:+d} for this investor.",
                            key_risks=scored["riskFactors"] or ["No major risk factor"],
                            suitable_for_investor=gap <= 0)

        prompt = (f"Stock risk (computed): {scored}. Investor capacity "
                  f"{profile['riskCapacityScore']}/100, constraints {profile['constraints']}. "
                  f"Suitability gap {gap:+d} (positive = riskier than this investor can hold). "
                  f"Market: {market.get('marketSummary')}. Fundamentals: "
                  f"{fund.get('fundamentalsSummary', 'n/a')}. News: {news.get('newsSummary', 'n/a')}"
                  "\nSummarise the key risks for this investor.")
        view, meta = self.decide(ctx, prompt, RiskView, fallback)
        return {**scored, "suitabilityGap": gap, "riskSummary": view.summary,
                "keyRisks": view.key_risks, "suitable": view.suitable_for_investor, "_llm": meta}

    def review(self, ctx, draft: dict, state: dict, round_: int, history: list[dict]) -> Critique:
        risk, cap = state["risk"], state.get("confidenceCap", "High")
        gap = risk["suitabilityGap"]

        def fallback():
            objections = []
            if draft["recommendation"] == "BUY":
                if risk["riskLevel"] == "High" and gap > 8:
                    objections.append(Objection(id="R1", severity="blocking",
                        text=f"BUY on a high-risk stock exceeds this investor's tolerance by {gap}."))
                elif gap > 0 or risk["riskScore"] >= 25:
                    objections.append(Objection(id="R1", severity="major",
                        text=f"Risk score {risk['riskScore']} is above this investor's "
                             f"comfortable level (gap {gap:+d}); justify or downgrade."))
            rank = {"Low": 0, "Moderate": 1, "High": 2}
            if rank[draft["confidence"]] > rank[cap]:
                objections.append(Objection(id="R2", severity="minor",
                    text=f"Confidence {draft['confidence']} exceeds what the data supports ({cap})."))
            if any(o.severity == "blocking" for o in objections):
                verdict = "veto"
            elif objections:
                verdict = "revise"
            else:
                verdict = "approve"
            return Critique(verdict=verdict, reasoning="Rule-based review.", objections=objections)

        past = "\n".join(f"Round {h['round']}: draft {h['draft']['recommendation']}, "
                         f"your verdict {h['critique']['verdict']} "
                         f"{[o['id'] + ': ' + o['text'] for o in h['critique']['objections']]}"
                         for h in history) or "none"
        prompt = (f"Round {round_}. Draft from Strategy: {draft}.\nRisk facts: score "
                  f"{risk['riskScore']} ({risk['riskLevel']}), factors {risk['riskFactors']}, "
                  f"suitability gap {gap:+d}, key risks {risk['keyRisks']}. Max confidence "
                  f"allowed by data quality: {cap}.\nEarlier rounds:\n{past}\n"
                  "Return your verdict and objections.")
        critique, meta = self.decide(ctx, prompt, Critique, fallback)

        # Deterministic guardrail on top of the LLM's judgement.
        if draft["recommendation"] == "BUY" and gap > HARD_LIMIT_GAP and critique.verdict == "approve":
            critique.verdict = "veto"
            critique.objections.append(Objection(id="G1", severity="blocking",
                text=f"Guardrail: suitability gap {gap} exceeds the hard limit {HARD_LIMIT_GAP}."))
            critique.reasoning += " Overridden by guardrail."
        if critique.verdict != "approve" and not critique.objections:
            critique.objections.append(Objection(id="R0", severity="minor",
                                                 text=critique.reasoning[:200]))
        ctx.emit(self.name, "StrategyAgent", "critique", critique.model_dump(), round_=round_,
                 llm=meta)
        return critique
