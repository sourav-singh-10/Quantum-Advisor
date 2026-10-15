r"""The agent graph (LangGraph).

    profile -> plan -> analysts -> assess --retry--> analysts      (Planner re-plans)
                                    |  \--no price--> abort
                                    v
                              risk_assess -> strategy -> review --revise/veto--> strategy
                                                            |  \--round limit--> arbitrate
                                                            v                      |
                                                         approve -> portfolio <----/
                                                                       -> report -> END

Edges marked with -- are conditional: the next step depends on what the agents decided.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

import config
from agents.fundamentals_agent import FundamentalsAnalyst
from agents.market_agent import MarketAnalyst
from agents.news_agent import NewsAnalyst
from agents.planner_agent import PlannerAgent
from agents.portfolio_agent import PortfolioAgent
from agents.profile_agent import ProfileAgent
from agents.report_agent import ReportAgent
from agents.risk_agent import RiskManager
from agents.strategy_agent import StrategyAgent
from core.context import RunContext
from tools.base import ToolError


class State(TypedDict, total=False):
    request: dict
    profile: dict
    lastRun: Any
    focus: str
    tasks: list
    results: dict
    errors: dict
    replans: int
    confidenceCap: str
    market: dict
    fundamentals: dict
    news: dict
    risk: dict
    round: int
    drafts: list
    debate: list
    final: dict
    portfolio: dict
    report: dict
    status: str


RESULT_KEYS = {  # what each analyst's result message carries in the trace
    "MarketAnalyst": ("currentPrice", "trend", "rsi", "volatility", "priceSource", "momentum",
                      "dataQuality", "marketSummary"),
    "FundamentalsAnalyst": ("pe", "roe", "de", "healthScore", "financialHealth",
                            "fundamentalsSummary"),
    "NewsAnalyst": ("newsSentiment", "headlineCount", "newsSource", "materialHeadlines",
                    "newsSummary"),
}
STATE_KEY = {"MarketAnalyst": "market", "FundamentalsAnalyst": "fundamentals",
             "NewsAnalyst": "news"}


def strip_private(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def build_graph(ctx: RunContext):
    planner, profile_agent = PlannerAgent(), ProfileAgent()
    analysts = {"MarketAnalyst": MarketAnalyst(), "FundamentalsAnalyst": FundamentalsAnalyst(),
                "NewsAnalyst": NewsAnalyst()}
    risk_mgr, strategist = RiskManager(), StrategyAgent()
    portfolio_agent, reporter = PortfolioAgent(), ReportAgent()

    # ------------------------------------------------------------ nodes
    def profile_node(state: State) -> State:
        req = state["request"]
        ctx.emit("Planner", "ProfileAgent", "task", {"instruction": "profile the investor"})
        prof = profile_agent.run(ctx, req)
        ctx.emit("ProfileAgent", "Planner", "result",
                 {k: prof[k] for k in ("riskCapacityScore", "profileSummary", "maxPositionPct",
                                       "constraints")}, llm=prof.get("_llm"))
        last = ctx.memory.last_run(ctx.user_key, req["ticker"]) if ctx.memory else None
        if last:
            ctx.emit("memory", "Planner", "memory", last)
        return {"profile": prof, "lastRun": last}

    def plan_node(state: State) -> State:
        plan = planner.plan(ctx, state["request"], state["profile"], state.get("lastRun"))
        return {"tasks": [t.model_dump() for t in plan.tasks], "focus": plan.focus,
                "results": {}, "errors": {}, "replans": 0}

    def run_one(task: dict, ticker: str) -> tuple[str, dict | None, str | None]:
        name, instruction = task["agent"], task["instruction"]
        ctx.emit("Planner", name, "task", {"instruction": instruction})
        try:
            out = analysts[name].run(ctx, ticker, instruction)
            ctx.emit(name, "Planner", "result",
                     {k: out.get(k) for k in RESULT_KEYS[name]}, llm=out.get("_llm"))
            return name, out, None
        except ToolError as exc:
            ctx.emit(name, "Planner", "error", {"error": str(exc)})
            return name, None, str(exc)
        except Exception as exc:  # an agent bug must not take the whole run down
            ctx.emit(name, "Planner", "error", {"error": f"{type(exc).__name__}: {exc}"})
            return name, None, f"{type(exc).__name__}: {exc}"

    def analysts_node(state: State) -> State:
        ticker = state["request"]["ticker"]
        results, errors = dict(state.get("results") or {}), dict(state.get("errors") or {})
        with ThreadPoolExecutor(max_workers=3) as pool:
            for name, out, err in pool.map(lambda t: run_one(t, ticker), state["tasks"]):
                if out is not None:
                    results[name] = out
                    errors.pop(name, None)
                else:
                    errors[name] = err
        return {"results": results, "errors": errors}

    def assess_node(state: State) -> State:
        a = planner.assess(ctx, state["results"], state["errors"], state.get("replans", 0))
        update: State = {"confidenceCap": a.confidence_cap}
        if a.action == "retry" and a.retries:
            update["tasks"] = [r.model_dump() for r in a.retries]
            update["replans"] = state.get("replans", 0) + 1
        else:
            update["tasks"] = []
            res = state["results"]
            for name, key in STATE_KEY.items():
                if name in res:
                    update[key] = res[name]
            ctx.failed.update(state["errors"].keys())
        return update

    def route_after_assess(state: State) -> str:
        if state.get("tasks"):
            return "analysts"
        return "risk_assess" if "market" in state else "abort"

    def abort_node(state: State) -> State:
        ctx.emit("Planner", "User", "final",
                 {"status": "failed", "reason": "No price data from any source.",
                  "errors": state["errors"]})
        return {"status": "failed"}

    def risk_node(state: State) -> State:
        ctx.emit("Planner", "RiskManager", "task", {"instruction": "assess risk for this investor"})
        risk = risk_mgr.assess(ctx, state)
        ctx.emit("RiskManager", "Planner", "result",
                 {k: risk[k] for k in ("riskScore", "riskLevel", "riskFactors", "suitabilityGap",
                                       "riskSummary")}, llm=risk.get("_llm"))
        return {"risk": risk, "round": 0, "drafts": [], "debate": []}

    def strategy_node(state: State) -> State:
        rnd = state["round"] + 1
        if rnd == 1:
            ctx.emit("Planner", "StrategyAgent", "task", {"instruction": state.get("focus", "")})
        last = state["debate"][-1] if state["debate"] else None
        draft = strategist.propose(ctx, state, rnd, last["critique"] if last else None,
                                   last["draft"] if last else None)
        return {"round": rnd, "drafts": state["drafts"] + [draft]}

    def review_node(state: State) -> State:
        draft = state["drafts"][-1]
        crit = risk_mgr.review(ctx, draft, state, state["round"], state["debate"])
        entry = {"round": state["round"],
                 "draft": {k: draft[k] for k in ("recommendation", "confidence", "rationale",
                                                 "responses")},
                 "critique": crit.model_dump()}
        return {"debate": state["debate"] + [entry]}

    def route_after_review(state: State) -> str:
        verdict = state["debate"][-1]["critique"]["verdict"]
        if verdict == "approve":
            return "approve"
        if state["round"] >= config.MAX_DEBATE_ROUNDS:
            return "arbitrate"
        return "strategy"

    def approve_node(state: State) -> State:
        final = {**state["drafts"][-1], "decidedBy": f"Risk approved in round {state['round']}"}
        ctx.emit("Planner", "team", "decision",
                 {"recommendation": final["recommendation"], "confidence": final["confidence"],
                  "decidedBy": final["decidedBy"]})
        return {"final": final}

    def arbitrate_node(state: State) -> State:
        drafts = [d["draft"] for d in state["debate"]]
        crits = [d["critique"] for d in state["debate"]]
        decision = planner.arbitrate(ctx, drafts, crits)
        from tools.position import price_targets
        m = state["market"]
        final = {**state["drafts"][-1], "recommendation": decision.recommendation,
                 "confidence": decision.confidence,
                 **price_targets(m["currentPrice"], m["volatility"], decision.recommendation),
                 "rationale": state["drafts"][-1]["rationale"] + [f"Planner: {decision.reasoning}"],
                 "decidedBy": f"Planner arbitration after {state['round']} rounds"}
        return {"final": final}

    def portfolio_node(state: State) -> State:
        ctx.emit("Planner", "PortfolioAgent", "task", {"instruction": "size the position"})
        out = portfolio_agent.run(ctx, state, state["request"])
        ctx.emit("PortfolioAgent", "Planner", "result",
                 {"portfolioAdvice": out["portfolioAdvice"], **out["positionSizing"]},
                 llm=out.get("_llm"))
        return {"portfolio": out}

    def report_node(state: State) -> State:
        ctx.emit("Planner", "ReportAgent", "task", {"instruction": "write the final report"})
        out = reporter.run(ctx, state)
        ctx.emit("ReportAgent", "User", "final", {"headline": out["reportHeadline"]},
                 llm=out.get("_llm"))
        return {"report": out, "status": "degraded" if (ctx.degraded or ctx.failed) else "ok"}

    # ------------------------------------------------------------ wiring
    g = StateGraph(State)
    for name, fn in [("profile", profile_node), ("plan", plan_node), ("analysts", analysts_node),
                     ("assess", assess_node), ("abort", abort_node), ("risk_assess", risk_node),
                     ("strategy", strategy_node), ("review", review_node),
                     ("approve", approve_node), ("arbitrate", arbitrate_node),
                     ("portfolio", portfolio_node), ("report", report_node)]:
        g.add_node(name, fn)
    g.add_edge(START, "profile")
    g.add_edge("profile", "plan")
    g.add_edge("plan", "analysts")
    g.add_edge("analysts", "assess")
    g.add_conditional_edges("assess", route_after_assess,
                            {"analysts": "analysts", "risk_assess": "risk_assess",
                             "abort": "abort"})
    g.add_edge("abort", END)
    g.add_edge("risk_assess", "strategy")
    g.add_edge("strategy", "review")
    g.add_conditional_edges("review", route_after_review,
                            {"approve": "approve", "arbitrate": "arbitrate",
                             "strategy": "strategy"})
    g.add_edge("approve", "portfolio")
    g.add_edge("arbitrate", "portfolio")
    g.add_edge("portfolio", "report")
    g.add_edge("report", END)
    return g.compile()
