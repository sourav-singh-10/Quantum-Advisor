"""Risk manager: scores risk with rule tools, judges suitability, and critiques Strategy."""
from __future__ import annotations

from agents.base import BaseAgent
from core.schemas import Critique, FollowUpRequest, Objection, RiskView
from tools.risk_rules import market_risk_score, suitability_gap

HARD_LIMIT_GAP = 15   # a BUY this far above the investor's tolerance is never approved


def open_questions(state: dict) -> list[FollowUpRequest]:
    """Questions the evidence leaves open, which an analyst could answer with its tools."""
    out, m = [], state["market"]
    ticker = m.get("ticker", "")
    news = state.get("news") or {}
    neg = [h["title"] for h in news.get("headlineLabels") or []
           if h.get("material") and h.get("sentiment") == "Negative"]
    if neg:
        out.append(FollowUpRequest(agent="NewsAnalyst",
            question=f"Is the headline '{neg[0][:120]}' about {ticker} itself, and could it move the price?",
            why="A negative headline about another company should not weigh on this decision."))
    move = m.get("change1mPct") or 0
    if abs(move) >= 8 or (m.get("rsi") or 50) >= 75:
        out.append(FollowUpRequest(agent="MarketAnalyst",
            question=f"The analysis window shows a {move:+.1f}% one-month move ({m.get('trend')}). Over a "
                     "full year, is this a breakout or a bounce inside a longer decline?",
            why="A short window can make a rebound look like a new uptrend."))
    if state.get("conflicts") and state.get("document"):
        out.append(FollowUpRequest(agent="DocumentAnalyst",
            question="What does the document say about the figures that disagree with the live data?",
            why="The filed figures and the live data point in different directions."))
    return out


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
        ctx.emit(self.name, "tool:market_risk_score", "tool_call", {"argument": "market+fund+news" + ("+document" if state.get("document") else "")})
        scored = market_risk_score(market, fund, news, state.get("document"),
                                   state.get("conflicts"))
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
                  f"{fund.get('fundamentalsSummary', 'n/a')}. News: {news.get('newsSummary', 'n/a')}. "
                  f"Document: {(state.get('document') or {}).get('documentSummary', 'none attached')}"
                  f"{'; conflicts with live data: ' + str([c['text'] for c in state['conflicts']]) if state.get('conflicts') else ''}"
                  "\nSummarise the key risks for this investor.")
        view, meta = self.decide(ctx, prompt, RiskView, fallback)
        return {**scored, "suitabilityGap": gap, "riskSummary": view.summary,
                "keyRisks": view.key_risks, "suitable": view.suitable_for_investor, "_llm": meta}

    def review(self, ctx, draft: dict, state: dict, round_: int, history: list[dict]) -> Critique:
        risk, cap = state["risk"], state.get("confidenceCap", "High")
        gap = risk["suitabilityGap"]
        answered = state.get("followups") or []
        asked_agents = {f["agent"] for f in answered}
        candidates = [q for q in open_questions(state) if q.agent in state.get("availableAnalysts", [])
                      and q.agent not in asked_agents]

        def fallback():
            objections = []
            if draft["recommendation"] == "BUY":
                if risk["riskLevel"] == "High" and gap > 8:
                    objections.append(Objection(id="R1", severity="blocking",
                        text=f"BUY on a high-risk stock exceeds this investor's tolerance by {gap}."))
                elif gap > 0:
                    objections.append(Objection(id="R1", severity="major",
                        text=f"Risk score {risk['riskScore']} is {gap} points above what this "
                             f"investor can comfortably carry; justify or downgrade."))
                elif risk["riskScore"] >= 25:
                    objections.append(Objection(id="R1", severity="major",
                        text=f"Risk score {risk['riskScore']} fits this investor but leaves only "
                             f"{-gap} points of headroom; justify the BUY or downgrade."))
            rsi = state["market"].get("rsi") or 50
            if draft["recommendation"] == "BUY" and rsi > 75:
                objections.append(Objection(id="R3", severity="major",
                    text=f"RSI {rsi:.0f} is strongly overbought; buying after a sharp run-up "
                         "risks entering at the top. Wait for a pullback or justify."))
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
            ask = None
            if draft["recommendation"] == "BUY" and candidates and not answered and can_ask:
                ask = candidates[0]          # check the shakiest evidence before backing a BUY
                if verdict == "approve":
                    verdict = "revise"
            return Critique(verdict=verdict, reasoning="Rule-based review.", objections=objections,
                            followup=ask)

        past = "\n".join(f"Round {h['round']}: draft {h['draft']['recommendation']}, "
                         f"your verdict {h['critique']['verdict']} "
                         f"{[o['id'] + ': ' + o['text'] for o in h['critique']['objections']]}"
                         for h in history) or "none"
        followups = "\n".join(f"- You/strategist asked {f['agent']}: {f['question']} -> {f['answer']}"
                              for f in answered) or "none"
        can_ask = state.get("followupsLeft", 0) > 0
        open_qs = "\n".join(f"- {q.agent}: {q.question} ({q.why})" for q in candidates) or "none"
        prompt = (f"Round {round_}. Draft from Strategy: {draft}.\nRisk facts: score "
                  f"{risk['riskScore']} ({risk['riskLevel']}), factors {risk['riskFactors']}, "
                  f"suitability gap {gap:+d}, key risks {risk['keyRisks']}. Max confidence "
                  f"allowed by data quality: {cap}.\nEarlier rounds:\n{past}\n"
                  f"Evidence gathered on request:\n{followups}\n"
                  + (f"Open questions an analyst could answer with its tools:\n{open_qs}\n"
                     "If one of them (or another specific question) could change your verdict, put it in "
                     "'followup'; the Planner will send that analyst and the debate continues with the "
                     "answer. Otherwise leave 'followup' empty.\n" if can_ask else
                     "No more follow-up questions are allowed; decide with what you have.\n")
                  + "Return your verdict and objections.")
        critique, meta = self.decide(ctx, prompt, Critique, fallback)

        # Deterministic guardrail on top of the LLM's judgement.
        if draft["recommendation"] == "BUY" and gap > HARD_LIMIT_GAP and critique.verdict == "approve":
            critique.verdict = "veto"
            critique.objections.append(Objection(id="G1", severity="blocking",
                text=f"Guardrail: suitability gap {gap} exceeds the hard limit {HARD_LIMIT_GAP}."))
            critique.reasoning += " Overridden by guardrail."
        if critique.followup and (not can_ask or critique.followup.agent not in
                                  state.get("availableAnalysts", [])):
            critique.followup = None
        if critique.verdict != "approve" and not critique.objections and not critique.followup:
            critique.objections.append(Objection(id="R0", severity="minor",
                                                 text=critique.reasoning[:200]))
        ctx.emit(self.name, "StrategyAgent", "critique", critique.model_dump(), round_=round_,
                 llm=meta)
        return critique
