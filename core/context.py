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

    def emit(self, *args, **kwargs):
        return self.tracer.emit(*args, **kwargs)
