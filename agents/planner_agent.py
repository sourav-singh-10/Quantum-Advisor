"""Planner (orchestrator agent): decides which analysts to run, judges their results,
re-plans after failures, and arbitrates when Strategy and Risk cannot agree."""
from __future__ import annotations

import config
from agents.base import BaseAgent
from core.schemas import (Arbitration, Assessment, FollowUpGrant, Plan, PlanTask, Reconciliation,
                          RetryTask)

ANALYSTS = ("MarketAnalyst", "FundamentalsAnalyst", "NewsAnalyst")
DOWNGRADE = {"BUY": "HOLD", "HOLD": "HOLD", "SELL": "SELL"}


class PlannerAgent(BaseAgent):
    name = "Planner"
    use_reasoning_model = True
    system = ("You coordinate a team of investment-analysis agents: MarketAnalyst (prices and "
              "indicators, always required), FundamentalsAnalyst (valuation, profitability, "
              "debt), NewsAnalyst (recent headlines) and DocumentAnalyst (reads a company "
              "document the investor uploaded; only available when one is attached). Plan only the work that helps this "
              "investor's decision, give each analyst a specific instruction, and re-plan when "
              "an analyst fails.")

    # ------------------------------------------------------------------ plan
    def plan(self, ctx, request: dict, profile: dict, last_run: dict | None,
             document: dict | None = None) -> Plan:
        available = ANALYSTS + (("DocumentAnalyst",) if document else ())

        def fallback():
            return Plan(reasoning="Default plan: run every available analyst.",
                        focus="Is this stock suitable for this investor now?",
                        tasks=[PlanTask(agent=a, instruction="standard analysis") for a in available])

        memory_note = (f"Previous analysis of {request['ticker']} by this user on "
                       f"{last_run['created_at']}: {last_run.get('recommendation')} with risk "
                       f"{last_run.get('riskScore')} and trend {last_run.get('trend')}."
                       if last_run else "No previous analysis of this ticker.")
        prompt = (f"Request: analyse NSE stock {request['ticker']}.\nInvestor: "
                  f"{profile['profileSummary']} Capacity {profile['riskCapacityScore']}/100, "
                  f"horizon ~{profile['horizonYears']} years, constraints {profile['constraints']}."
                  f"\nMemory: {memory_note}\nDecide which analysts to run and what each should "
                  "focus on. Fundamentals matter most for long horizons; news matters most for "
                  "short horizons. MarketAnalyst is mandatory."
                  + (f"\nThe investor attached '{document['name']}' ({document['pageCount']} "
                     "pages): give DocumentAnalyst a specific reading brief."
                     if document else "\nNo document is attached, so DocumentAnalyst cannot run."))
        plan, meta = self.decide(ctx, prompt, Plan, fallback)
        if not document:
            plan.tasks = [t for t in plan.tasks if t.agent != "DocumentAnalyst"]
        elif not any(t.agent == "DocumentAnalyst" for t in plan.tasks):
            plan.tasks.append(PlanTask(agent="DocumentAnalyst",
                                       instruction="read the attached document"))
            plan.reasoning += " (DocumentAnalyst added: the investor attached a document.)"
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
                    "fundamentalsSummary", "newsSentiment", "headlineCount", "newsSummary",
                    "documentSummary", "documentRedFlags")
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

    # ------------------------------------------------------------------ reconcile
    def reconcile(self, ctx, issues: list[dict], document: dict, fundamentals: dict,
                  current_cap: str) -> Reconciliation:
        """Decide which figures to rely on when the document and live data disagree."""
        def fallback():
            return Reconciliation(
                reasoning="The document and the live data cover different periods or bases "
                          "(a filed statement versus trailing-twelve-month data), so neither "
                          "is wrong; the committee notes both and claims less certainty.",
                trust="both", confidence_cap="Moderate" if current_cap != "Low" else "Low")

        prompt = ("The DocumentAnalyst challenged the FundamentalsAnalyst:\n"
                  + "\n".join(f"- {i['text']}" for i in issues)
                  + f"\nDocument: {document['documentName']}, period "
                    f"{document.get('documentPeriod') or 'not stated'}. Live data: Yahoo Finance "
                    f"trailing figures. Current confidence cap: {current_cap}.\nDecide which "
                    "figures the committee should rely on and cap the confidence accordingly.")
        decision, meta = self.decide(ctx, prompt, Reconciliation, fallback)
        rank = {"Low": 0, "Moderate": 1, "High": 2}
        if rank[decision.confidence_cap] > rank[current_cap]:
            decision.confidence_cap = current_cap   # a conflict can never raise confidence
        ctx.emit(self.name, "team", "reconciliation", decision.model_dump(), llm=meta)
        return decision

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
            for i, (d, c) in enumerate(zip(drafts, critiques, strict=False)))
        prompt = (f"Strategy and Risk did not agree within {len(drafts)} rounds.\n{history}\n"
                  "Decide the final recommendation. When in doubt, protect the investor: that means "
                  "no new money (HOLD), not SELL. Choose SELL only if the stock's own outlook is weak.")
        decision, meta = self.decide(ctx, prompt, Arbitration, fallback)
        if last_crit["verdict"] == "veto" and decision.recommendation == "BUY":
            decision.recommendation, decision.confidence = "HOLD", "Low"
            decision.reasoning += " (Guardrail: a vetoed BUY cannot be final.)"
        ctx.emit(self.name, "team", "arbitration", decision.model_dump(), llm=meta)
        return decision

    # ------------------------------------------------------------------ follow-up requests
    def route_followup(self, ctx, requester: str, request: dict, available: list[str],
                       done: list[dict]) -> FollowUpGrant:
        """Decide whether to send an analyst back for more evidence, and what exactly to ask."""
        agent, question = request["agent"], request["question"]
        repeated = any(d["agent"] == agent and d["question"].lower() == question.lower() for d in done)

        def fallback():
            ok = agent in available and not repeated
            return FollowUpGrant(grant=ok, agent=agent if agent in available else available[0],
                                 instruction=question,
                                 reasoning=("The answer could change the decision; sending it to "
                                            f"{agent}." if ok else
                                            "Declined: the same question was already answered."
                                            if repeated else f"{agent} is not part of this analysis."))

        asked = "\n".join(f"- {d['agent']}: {d['question']} -> {d['answer']}" for d in done) or "none"
        prompt = (f"{requester} asks for more evidence before the next round.\n"
                  f"Request: {agent}: {question}\nWhy: {request.get('why', '')}\n"
                  f"Analysts available in this run: {', '.join(available)}.\n"
                  f"Follow-ups already answered:\n{asked}\n"
                  "Grant it if the answer could change the decision and it is not a repeat; you may "
                  "redirect it to a better-suited analyst and sharpen the question into a task.")
        grant, meta = self.decide(ctx, prompt, FollowUpGrant, fallback)
        if grant.agent not in available:              # never route to an analyst who is not here
            grant.agent, grant.grant = agent if agent in available else available[0], grant.grant and agent in available
        if repeated:
            grant.grant = False
        ctx.emit(self.name, requester, "decision",
                 {"followup": "granted" if grant.grant else "declined", "agent": grant.agent,
                  "instruction": grant.instruction, "reasoning": grant.reasoning}, llm=meta)
        return grant
