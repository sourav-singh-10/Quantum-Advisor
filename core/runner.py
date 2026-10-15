"""Entry point used by the Flask app and the tests: runs one analysis end to end."""
from __future__ import annotations

import time
from typing import Optional

from core.context import RunContext
from core.graph import build_graph, strip_private
from core.memory import RunMemory
from core.tracer import Tracer
from services.llm_service import LLMClient

REC_CLASS = {"BUY": "buy", "HOLD": "hold", "SELL": "sell"}


def run_analysis(request: dict, user_key: str = "anonymous", llm: Optional[LLMClient] = None,
                 tracer: Optional[Tracer] = None, memory: Optional[RunMemory] = None) -> dict:
    """``request`` must already be validated (core.schemas.AnalyzeRequest)."""
    started = time.monotonic()
    llm = llm or LLMClient()
    tracer = tracer or Tracer()
    ctx = RunContext(llm=llm, tracer=tracer, memory=memory, user_key=user_key)
    ctx.emit("User", "Planner", "request", request)

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
    }
    if state.get("status") == "failed":
        return {"ticker": request["ticker"], "error": "Could not get price data for "
                f"{request['ticker']} from any source. Check the symbol (NSE code, e.g. RELIANCE).",
                "errors": state.get("errors", {}), "meta": meta, "trace": tracer.events}

    final, risk = state["final"], state["risk"]
    response = {
        # flat fields kept for the existing frontend
        **strip_private(state["profile"]),
        **strip_private(state["market"]),
        **strip_private(state.get("fundamentals") or {"financialHealth": "Not analysed"}),
        **strip_private(state.get("news") or {"newsSentiment": "Not analysed"}),
        **strip_private(risk),
        "recommendation": final["recommendation"],
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
        "lastRun": state.get("lastRun"),
        "meta": meta,
        "trace": tracer.events,
    }
    if memory:
        memory.save(tracer.run_id, user_key, request["ticker"],
                    {"recommendation": final["recommendation"], "riskScore": risk["riskScore"],
                     "trend": state["market"]["trend"],
                     "price": state["market"]["currentPrice"]})
    return response
