"""Planner (orchestrator agent): decides which analysts to run, judges their results,
re-plans after failures, and arbitrates when Strategy and Risk cannot agree."""
from __future__ import annotations

import config
from agents.base import BaseAgent
from core.schemas import Arbitration, Assessment, Plan, PlanTask, RetryTask

ANALYSTS = ("MarketAnalyst", "FundamentalsAnalyst", "NewsAnalyst")
DOWNGRADE = {"BUY": "HOLD", "HOLD": "HOLD", "SELL": "SELL"}


class PlannerAgent(BaseAgent):
    name = "Planner"
    use_reasoning_model = True
    system = ("You coordinate a team of investment-analysis agents: MarketAnalyst (prices and "
              "indicators, always required), FundamentalsAnalyst (valuation, profitability, "
              "debt) and NewsAnalyst (recent headlines). Plan only the work that helps this "
              "investor's decision, give each analyst a specific instruction, and re-plan when "
              "an analyst fails.")

    # ------------------------------------------------------------------ plan
    def plan(self, ctx, request: dict, profile: dict, last_run: dict | None) -> Plan:
        def fallback():
            return Plan(reasoning="Default plan: run every analyst.",
                        focus="Is this stock suitable for this investor now?",
                        tasks=[PlanTask(agent=a, instruction="standard analysis") for a in ANALYSTS])

        memory_note = (f"Previous analysis of {request['ticker']} by this user on "
                       f"{last_run['created_at']}: {last_run.get('recommendation')} with risk "
                       f"{last_run.get('riskScore')} and trend {last_run.get('trend')}."
                       if last_run else "No previous analysis of this ticker.")
        prompt = (f"Request: analyse NSE stock {request['ticker']}.\nInvestor: "
                  f"{profile['profileSummary']} Capacity {profile['riskCapacityScore']}/100, "
                  f"horizon ~{profile['horizonYears']} years, constraints {profile['constraints']}."
                  f"\nMemory: {memory_note}\nDecide which analysts to run and what each should "
                  "focus on. Fundamentals matter most for long horizons; news matters most for "
                  "short horizons. MarketAnalyst is mandatory.")
        plan, meta = self.decide(ctx, prompt, Plan, fallback)
        if not any(t.agent == "MarketAnalyst" for t in plan.tasks):
            plan.tasks.insert(0, PlanTask(agent="MarketAnalyst", instruction="standard analysis"))
            plan.reasoning += " (MarketAnalyst added: price data is mandatory.)"
        seen, unique = set(), []
        for t in plan.tasks:
            if t.agent not in seen:
                seen.add(t.agent)
                unique.append(t)
        plan.tasks = unique
        ctx.emit(self.name, "team", "plan", plan.model_dump(), llm=meta)
        return plan

    # ------------------------------------------------------------------ assess / re-plan
    def assess(self, ctx, results: dict, errors: dict, replans_done: int) -> Assessment:
        can_retry = replans_done < config.MAX_REPLANS

        def fallback():
            retries = [RetryTask(agent=a, instruction=f"Retry once; previous error: {e[:120]}")
                       for a, e in errors.items()] if can_retry else []
            missing = len(errors) + sum(1 for r in results.values()
                                        if r.get("fundamentalsAvailable") is False
                                        or r.get("newsAvailable") is False)
            cap = "Low" if "MarketAnalyst" in errors or missing >= 2 else \
                  "Moderate" if missing == 1 else "High"
            return Assessment(reasoning="Rule check of analyst results.",
                              action="retry" if retries else "proceed",
                              retries=retries, confidence_cap=cap)

        lines = []
        for agent, r in results.items():
            keys = ("trend", "rsi", "volatility", "dataQuality", "priceSource", "financialHealth",
                    "fundamentalsSummary", "newsSentiment", "headlineCount", "newsSummary")
            lines.append(f"{agent}: " + str({k: r[k] for k in keys if k in r}))
        for agent, err in errors.items():
            lines.append(f"{agent}: FAILED - {err}")
        prompt = ("Analyst results:\n" + "\n".join(lines) +
                  f"\nRe-plans used: {replans_done}/{config.MAX_REPLANS}. Decide: proceed, or "
                  "retry specific analysts with a different instruction (e.g. a different data "
                  "source). Retry only if it could change the outcome. Also cap the confidence "
                  "the final recommendation may claim, given data quality.")
        assessment, meta = self.decide(ctx, prompt, Assessment, fallback)
        if not can_retry or assessment.action == "proceed":
            assessment.action, assessment.retries = "proceed", []
        ctx.emit(self.name, "team", "assessment", assessment.model_dump(), llm=meta)
        if assessment.action == "retry":
            for r in assessment.retries:
                ctx.emit(self.name, r.agent, "replan", {"instruction": r.instruction})
        return assessment

    # ------------------------------------------------------------------ arbitrate
    def arbitrate(self, ctx, drafts: list[dict], critiques: list[dict]) -> Arbitration:
        last_draft, last_crit = drafts[-1], critiques[-1]

        def fallback():
            rec = DOWNGRADE[last_draft["recommendation"]] if last_crit["verdict"] != "approve" \
                else last_draft["recommendation"]
            return Arbitration(reasoning="No agreement after the round limit; taking the more "
                                         "conservative position.",
                               recommendation=rec, confidence="Low")

        history = "\n".join(
            f"Round {i + 1}: Strategy {d['recommendation']} ({d['confidence']}): {d['rationale']}"
            f"\n  Risk {c['verdict']}: {[o['text'] for o in c['objections']]}"
            for i, (d, c) in enumerate(zip(drafts, critiques)))
        prompt = (f"Strategy and Risk did not agree within {len(drafts)} rounds.\n{history}\n"
                  "Decide the final recommendation. When in doubt, protect the investor.")
        decision, meta = self.decide(ctx, prompt, Arbitration, fallback)
        if last_crit["verdict"] == "veto" and decision.recommendation == "BUY":
            decision.recommendation, decision.confidence = "HOLD", "Low"
            decision.reasoning += " (Guardrail: a vetoed BUY cannot be final.)"
        ctx.emit(self.name, "team", "arbitration", decision.model_dump(), llm=meta)
        return decision
