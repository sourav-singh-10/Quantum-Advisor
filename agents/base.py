"""BaseAgent: structured LLM decisions with rule fallback, and a ReAct-style tool loop.

Every agent in Quantum Advisor follows the same contract:
  * the LLM decides (which tool, what it means, what to recommend);
  * tools do the maths and the data fetching, so numbers are never invented;
  * if the LLM is unavailable or answers badly, the agent falls back to its rule-based
    path, marks itself as degraded, and the trace says so.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional, Type

from pydantic import BaseModel

import config
from core.context import RunContext
from core.schemas import FollowUpAnswer, ToolStep
from tools.base import ToolError
from tools.safety import SYSTEM_NOTE


@dataclass
class Tool:
    name: str
    description: str
    run: Callable[[str], Any]
    summarize: Callable[[Any], str] = lambda r: json.dumps(r, default=str)[:400]


class BaseAgent:
    name = "Agent"
    reports_to = "Planner"
    use_reasoning_model = False
    system = "You are a careful financial analysis agent."

    # ------------------------------------------------------------ one decision
    def decide(self, ctx: RunContext, prompt: str, schema: Type[BaseModel],
               fallback: Callable[[], BaseModel]) -> tuple[BaseModel, dict]:
        res = ctx.llm.structured(agent=self.name, system=self.system + SYSTEM_NOTE, prompt=prompt,
                                 schema=schema, reasoning=self.use_reasoning_model)
        meta = {"model": res.model, "latency_ms": res.latency_ms, "ok": res.value is not None}
        if res.value is not None:
            return res.value, meta
        ctx.degraded.add(self.name)
        meta.update({"fallback": "rules", "error": res.error})
        return fallback(), meta

    # ------------------------------------------------------------ follow-up questions
    def use_tool(self, ctx: RunContext, name: str, argument: str, fn: Callable[[], Any],
                 summarize: Callable[[Any], str]):
        """Call one tool and trace it; returns None when the tool fails."""
        ctx.emit(self.name, f"tool:{name}", "tool_call", {"argument": argument})
        try:
            if ctx.simulated_tool_failure(name, argument):
                raise ToolError(f"simulated outage of {name} (evaluation mode)")
            out = fn()
        except ToolError as exc:
            ctx.emit(f"tool:{name}", self.name, "tool_result", {"ok": False, "error": str(exc)})
            return None
        ctx.emit(f"tool:{name}", self.name, "tool_result", {"ok": True, "summary": summarize(out)})
        return out

    def followup_facts(self, ctx: RunContext, ticker: str, question: str,
                       previous: dict) -> tuple[list[str], str]:
        """Facts (gathered with tools) that bear on a follow-up question, and a rule answer.
        Analysts override this; the default restates what the analyst already found."""
        facts = [f"{k}: {v}" for k, v in previous.items()
                 if not k.startswith("_") and isinstance(v, (str, int, float)) and v not in ("", None)][:14]
        return facts, (facts[0] if facts else "No further information is available.")

    def follow_up(self, ctx: RunContext, ticker: str, question: str, previous: dict) -> dict:
        """Answer a question another agent asked through the Planner."""
        facts, rule_answer = self.followup_facts(ctx, ticker, question, previous or {})

        def fallback():
            return FollowUpAnswer(answer=rule_answer, evidence=facts[:4], changes_view=False)

        prompt = (f"Question from the investment committee about {ticker}: {question}\n"
                  "Facts from your tools:\n- " + "\n- ".join(facts or ["(no facts available)"]) +
                  "\nAnswer directly, using only these facts. Say so if they cannot answer it.")
        ans, meta = self.decide(ctx, prompt, FollowUpAnswer, fallback)
        return {**ans.model_dump(), "_llm": meta}

    # ------------------------------------------------------------ tool loop
    def tool_loop(self, ctx: RunContext, goal: str, tools: list[Tool],
                  default_plan: list[tuple[str, str]],
                  done: Callable[[list[dict]], bool]) -> list[dict]:
        """Let the LLM choose tools until it says 'finish' (max MAX_TOOL_STEPS).

        Without an LLM, run ``default_plan`` in order until ``done`` is satisfied.
        Returns the list of observations: {tool, argument, ok, result|error}.
        """
        by_name = {t.name: t for t in tools}
        observations: list[dict] = []
        catalog = "\n".join(f"- {t.name}(argument): {t.description}" for t in tools)

        for _ in range(config.MAX_TOOL_STEPS):
            history = "\n".join(
                f"{i + 1}. {o['tool']}({o['argument']}) -> "
                + (f"OK: {o['summary']}" if o["ok"] else f"FAILED: {o['error']}")
                for i, o in enumerate(observations)) or "(none yet)"
            prompt = (f"Goal: {goal}\n\nTools:\n{catalog}\n- finish: stop when you have what "
                      f"you need, or when nothing else can help.\n\nObservations so far:\n"
                      f"{history}\n\nChoose the next action.")
            res = ctx.llm.structured(agent=self.name, system=self.system + SYSTEM_NOTE, prompt=prompt,
                                     schema=ToolStep)
            if res.value is None:
                ctx.degraded.add(self.name)
                ctx.emit(self.name, self.name, "decision",
                         {"note": "LLM unavailable; following default tool order",
                          "error": res.error},
                         llm={"model": res.model, "ok": False})
                return self._run_default(ctx, by_name, default_plan, done, observations)
            step: ToolStep = res.value
            llm_meta = {"model": res.model, "latency_ms": res.latency_ms, "ok": True}
            if step.action == "finish":
                payload = {"thought": step.thought, "action": "finish"}
                if not any(o["ok"] for o in observations):
                    # The LLM's own words are not evidence: record what actually happened.
                    payload["check"] = ("No tool call has succeeded yet, so the remaining "
                                        "sources are tried before giving up.")
                ctx.emit(self.name, self.name, "decision", payload, llm=llm_meta)
                break
            if step.action not in by_name:
                observations.append({"tool": step.action, "argument": step.argument,
                                     "ok": False, "error": "no such tool"})
                continue
            self._call(ctx, by_name[step.action], step.argument, observations,
                       thought=step.thought, llm=llm_meta)
            if done(observations):
                # Goal met: no need to spend another LLM call just to say "finish".
                break
        if not done(observations) and not any(o["ok"] for o in observations):
            # LLM gave up early; make sure every default option was at least tried.
            self._run_default(ctx, by_name, default_plan, done, observations)
        return observations

    def _run_default(self, ctx, by_name, default_plan, done, observations):
        tried = {(o["tool"], o["argument"]) for o in observations}
        for tool_name, arg in default_plan:
            if done(observations):
                break
            if (tool_name, arg) in tried:
                continue
            self._call(ctx, by_name[tool_name], arg, observations, thought="default order")
        return observations

    def _call(self, ctx, tool: Tool, argument: str, observations: list, thought: str,
              llm: Optional[dict] = None):
        ctx.emit(self.name, f"tool:{tool.name}", "tool_call",
                 {"argument": argument, "thought": thought}, llm=llm)
        try:
            if ctx.simulated_tool_failure(tool.name, argument):
                raise ToolError(f"simulated outage of {tool.name}({argument}) (evaluation mode)")
            result = tool.run(argument)
            summary = tool.summarize(result)
            observations.append({"tool": tool.name, "argument": argument, "ok": True,
                                 "result": result, "summary": summary})
            ctx.emit(f"tool:{tool.name}", self.name, "tool_result",
                     {"ok": True, "summary": summary})
        except ToolError as exc:
            observations.append({"tool": tool.name, "argument": argument, "ok": False,
                                 "error": str(exc)})
            ctx.emit(f"tool:{tool.name}", self.name, "tool_result",
                     {"ok": False, "error": str(exc)})
