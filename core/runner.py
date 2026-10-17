"""Entry point used by the Flask app and the tests: runs one analysis end to end."""
from __future__ import annotations

import time
from typing import Optional

from core.context import RunContext
from core.graph import build_graph, strip_private
from core.memory import RunMemory
from core.tracer import Tracer
from services.llm_service import LLMClient
from tools.market_data import RENAMED
from tools.preferences import avoid_matches
from tools.actions import action_for
from tools.scorecard import scorecard

REC_CLASS = {"BUY": "buy", "HOLD": "hold", "SELL": "sell"}


def run_analysis(request: dict, user_key: str = "anonymous", llm: Optional[LLMClient] = None,
                 tracer: Optional[Tracer] = None, memory: Optional[RunMemory] = None,
                 document: Optional[dict] = None, faults: frozenset = frozenset()) -> dict:
    """``request`` must already be validated (core.schemas.AnalyzeRequest).

    ``document`` is an uploaded company PDF already read by tools.document_data.load_pdf.
    """
    started = time.monotonic()
    llm = llm or LLMClient()
    tracer = tracer or Tracer()
    ctx = RunContext(llm=llm, tracer=tracer, memory=memory, user_key=user_key, document=document,
                     faults=frozenset(faults))
    ctx.emit("User", "Planner", "request",
             {**request, **({"document": f"{document['name']} ({document['pageCount']} pages)"}
                            if document else {})})
    if faults:
        ctx.emit("Planner", "team", "decision",
                 {"note": "Evaluation mode: simulated failures for this run: " + ", ".join(sorted(faults))
                          + ". They test how the team adapts; they are not real outages."})
    new_symbol = RENAMED.get(request["ticker"].upper())
    if new_symbol:
        ctx.emit("Planner", "team", "decision",
                 {"note": f"{request['ticker']} no longer trades under that symbol; it is now "
                          f"{new_symbol}, so the team will analyse {new_symbol}."})
        request = {**request, "ticker": new_symbol, "requestedTicker": request["ticker"]}

    state = build_graph(ctx).invoke({"request": request}, config={"recursion_limit": 60})
    meta = {
        "runId": tracer.run_id,
        "status": state.get("status", "failed"),
        "llmAvailable": llm.available,
        "llmCalls": llm.stats.calls,
        "llmFailures": llm.stats.failures,
        "degradedAgents": sorted(ctx.degraded),
        "failedAgents": sorted(ctx.failed | set((state.get("errors") or {}).keys())
                               if state.get("status") == "failed" else ctx.failed),
        "durationMs": int((time.monotonic() - started) * 1000),
        "replans": state.get("replans", 0),
        "debateRounds": state.get("round", 0),
        "followups": len(state.get("followups") or []),
        "models": dict(llm.stats.models),
    }
    if state.get("status") == "failed":
        hint = RENAMED.get(request["ticker"].upper())
        hint = (f" {request['ticker']} now trades as {hint}; try that code." if hint
                else " Check the symbol (NSE code, e.g. RELIANCE).")
        return {"ticker": request["ticker"], "error": "Could not get price data for "
                f"{request['ticker']} from any source.{hint}",
                "errors": state.get("errors", {}), "meta": meta, "trace": tracer.events}

    final, risk = state["final"], state["risk"]
    fund = state.get("fundamentals") or {}
    preference_notes = avoid_matches(request.get("avoidSectors"), request["ticker"],
                                     fund.get("sector"), fund.get("companyName"))
    if preference_notes:
        ctx.emit("Planner", "User", "decision",
                 {"note": " ".join(preference_notes) + " The recommendation is unchanged; the choice is yours."})
    response = {
        # flat fields kept for the existing frontend
        **strip_private(state["profile"]),
        **strip_private(state["market"]),
        **strip_private(state.get("fundamentals") or {"financialHealth": "Not analysed"}),
        **strip_private(state.get("news") or {"newsSentiment": "Not analysed"}),
        **strip_private(state.get("document") or {"documentAvailable": False}),
        "documentConflicts": [c["text"] for c in state.get("conflicts") or []],
        "requestedTicker": request.get("requestedTicker", request["ticker"]),
        "preferenceNotes": preference_notes,
        **strip_private(risk),
        "recommendation": final["recommendation"],
        "holding": bool(request.get("holding")),
        "action": action_for(final["recommendation"], request.get("holding"), risk["suitabilityGap"]),
        "recommendationClass": REC_CLASS[final["recommendation"]],
        "confidence": final["confidence"],
        "decidedBy": final["decidedBy"],
        "buyScore": final["buyScore"],
        "targetPrice1": final["targetPrice1"],
        "targetPrice2": final["targetPrice2"],
        "stopLoss": final["stopLoss"],
        "reasoning": final["rationale"],
        **strip_private(state["portfolio"]),
        **strip_private(state["report"]),
        # agentic evidence
        "plan": {"focus": state.get("focus"), "replans": state.get("replans", 0)},
        "debate": state["debate"],
        "followups": state.get("followups") or [],
        "lastRun": state.get("lastRun"),
        "meta": meta,
        "trace": tracer.events,
    }
    response["scorecard"] = scorecard(response)
    if memory:
        memory.save(tracer.run_id, user_key, request["ticker"],
                    {"recommendation": final["recommendation"], "riskScore": risk["riskScore"],
                     "trend": state["market"]["trend"],
                     "price": state["market"]["currentPrice"]})
    return response
