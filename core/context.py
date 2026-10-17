"""Per-run context handed to every agent: the LLM, the tracer, memory and bookkeeping."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.memory import RunMemory
from core.tracer import Tracer
from services.llm_service import LLMClient


@dataclass
class RunContext:
    llm: LLMClient
    tracer: Tracer
    memory: Optional[RunMemory] = None
    user_key: str = "anonymous"
    degraded: set = field(default_factory=set)      # agents that fell back to rules
    failed: set = field(default_factory=set)        # agents that produced no result
    document: Optional[dict] = None                 # uploaded company PDF, as page texts
    # Simulated failures for the evaluation (only when the server enables EVAL_FAULTS):
    # "tool:<tool>[:<source>]" fails that tool's first call (a short outage);
    # "agent:<name>" makes that analyst's first attempt fail, so the Planner must re-plan.
    faults: frozenset = frozenset()
    _fired: set = field(default_factory=set)

    def simulated_tool_failure(self, tool: str, argument: str) -> bool:
        source = (argument or "").split(":")[0].strip().lower()     # "yfinance:TCS" -> "yfinance"
        for key in (f"tool:{tool}", f"tool:{tool}:{source}"):
            if key in self.faults and key not in self._fired:
                self._fired.add(key)
                return True
        return False

    def simulated_agent_failure(self, agent: str) -> bool:
        key = f"agent:{agent}"
        if key in self.faults and key not in self._fired:
            self._fired.add(key)
            return True
        return False

    def emit(self, *args, **kwargs):
        return self.tracer.emit(*args, **kwargs)
