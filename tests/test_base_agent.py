from agents.base import BaseAgent, Tool
from core.context import RunContext
from core.schemas import MarketView
from core.tracer import Tracer
from tests.fakes import FakeLLM
from tools.base import ToolError


def ctx_with(llm, tmp_path):
    return RunContext(llm=llm, tracer=Tracer(log_dir=tmp_path))


def flaky_tool():
    def run(arg):
        if arg == "bad":
            raise ToolError("bad source")
        return [1, 2, 3]
    return Tool(name="fetch", description="test", run=run, summarize=lambda r: f"{len(r)} items")


def test_decide_falls_back_and_marks_agent_degraded(tmp_path):
    ctx = ctx_with(FakeLLM(available=False), tmp_path)
    agent = BaseAgent()
    view, meta = agent.decide(ctx, "p", MarketView, lambda: MarketView(
        summary="rules", momentum="Flat", data_quality="Good"))
    assert view.summary == "rules" and meta["fallback"] == "rules"
    assert "Agent" in ctx.degraded


def test_tool_loop_follows_llm_choice_and_stops_when_done(tmp_path):
    llm = FakeLLM({("Agent", "ToolStep"): [
        {"thought": "try bad", "action": "fetch", "argument": "bad"},
        {"thought": "bad failed, try good", "action": "fetch", "argument": "good"}]})
    ctx = ctx_with(llm, tmp_path)
    obs = BaseAgent().tool_loop(ctx, "get data", [flaky_tool()], [("fetch", "good")],
                                lambda o: any(x["ok"] for x in o))
    assert [(o["argument"], o["ok"]) for o in obs] == [("bad", False), ("good", True)]
    assert len(llm.calls) == 2          # no extra call just to say "finish"
    second_prompt = llm.calls[1][2]
    assert "FAILED: bad source" in second_prompt   # the LLM saw the failure


def test_tool_loop_without_llm_uses_default_order(tmp_path):
    ctx = ctx_with(FakeLLM(available=False), tmp_path)
    obs = BaseAgent().tool_loop(ctx, "get data", [flaky_tool()],
                                [("fetch", "bad"), ("fetch", "good"), ("fetch", "never")],
                                lambda o: any(x["ok"] for x in o))
    assert [o["argument"] for o in obs] == ["bad", "good"]


def test_unknown_tool_is_reported_back_not_crashing(tmp_path):
    llm = FakeLLM({("Agent", "ToolStep"): [
        {"thought": "?", "action": "teleport", "argument": ""},
        {"thought": "ok", "action": "fetch", "argument": "good"}]})
    obs = BaseAgent().tool_loop(ctx_with(llm, tmp_path), "g", [flaky_tool()], [],
                                lambda o: any(x["ok"] for x in o))
    assert obs[0]["error"] == "no such tool" and obs[1]["ok"]
