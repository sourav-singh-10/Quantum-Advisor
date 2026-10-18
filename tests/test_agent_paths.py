"""The agentic behaviours the CA3 rubric asks for, each exercised with a scripted LLM."""
from core.runner import run_analysis
from core.schemas import AnalyzeRequest
from tests.fakes import FUNDAMENTALS, FakeLLM, patch_data

REQ = AnalyzeRequest(ticker="TESTCO").model_dump()

PLAN = {"reasoning": "Medium horizon: all three matter.", "focus": "Suitability now",
        "tasks": [{"agent": "MarketAnalyst", "instruction": "trend"},
                  {"agent": "FundamentalsAnalyst", "instruction": "debt"},
                  {"agent": "NewsAnalyst", "instruction": "material news"}]}
PROCEED = {"reasoning": "Data is good.", "action": "proceed", "retries": [],
           "confidence_cap": "High"}
BUY = {"recommendation": "BUY", "confidence": "High", "rationale": ["uptrend", "strong ROE"],
       "responses": []}
HOLD = {"recommendation": "HOLD", "confidence": "Moderate", "rationale": ["risk too high"],
        "responses": [{"objection_id": "R1", "response": "Accepted, moved to HOLD."}]}
REVISE = {"verdict": "revise", "reasoning": "Too aggressive.",
          "objections": [{"id": "R1", "text": "Volatility too high for a beginner",
                          "severity": "major"}]}
APPROVE = {"verdict": "approve", "reasoning": "Resolved.", "objections": []}
VETO = {"verdict": "veto", "reasoning": "Harmful.",
        "objections": [{"id": "R1", "text": "Unsuitable", "severity": "blocking"}]}


def events(out, type_=None):
    return [e for e in out["trace"] if type_ is None or e["type"] == type_]


def test_revision_round_changes_recommendation(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco wins order"])
    llm = FakeLLM({("Planner", "Plan"): [PLAN], ("Planner", "Assessment"): [PROCEED],
                   ("StrategyAgent", "StrategyDraft"): [BUY, HOLD],
                   ("RiskManager", "Critique"): [REVISE, APPROVE]})
    out = run_analysis(REQ, llm=llm)
    assert out["recommendation"] == "HOLD"
    assert out["decidedBy"] == "Risk approved in round 2"
    assert [d["critique"]["verdict"] for d in out["debate"]] == ["revise", "approve"]
    drafts = events(out, "draft")
    assert [d["round"] for d in drafts] == [1, 2]
    # Strategy saw the critique in round 2
    round2_prompt = [p for a, s, p in llm.calls if a == "StrategyAgent"][1]
    assert "R1" in round2_prompt and "Volatility too high" in round2_prompt
    assert out["portfolioAdvice"] and not any("Buy up to" in a for a in out["portfolioAdvice"])


def test_round_limit_leads_to_planner_arbitration(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco wins order"])
    llm = FakeLLM({("Planner", "Plan"): [PLAN], ("Planner", "Assessment"): [PROCEED],
                   ("StrategyAgent", "StrategyDraft"): [BUY, BUY, BUY],
                   ("RiskManager", "Critique"): [VETO, VETO, VETO],
                   ("Planner", "Arbitration"): [{"reasoning": "Strategy is right",
                                                 "recommendation": "BUY",
                                                 "confidence": "High"}]})
    out = run_analysis(REQ, llm=llm)
    assert len(out["debate"]) == 3
    assert out["decidedBy"].startswith("Planner arbitration")
    # guardrail: a vetoed BUY cannot be the final answer, whatever the LLM says
    assert out["recommendation"] == "HOLD" and out["confidence"] == "Low"
    assert events(out, "arbitration")


def test_planner_skips_analysts_it_does_not_need(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["x"])
    plan = {"reasoning": "Short horizon: price only.", "focus": "Timing",
            "tasks": [{"agent": "NewsAnalyst", "instruction": "x"}]}   # forgot Market
    llm = FakeLLM({("Planner", "Plan"): [plan]})
    out = run_analysis(REQ, llm=llm)
    tasks = {e["to"] for e in events(out, "task")}
    assert "MarketAnalyst" in tasks            # mandatory analyst added back
    assert "FundamentalsAnalyst" not in tasks  # skipped on the Planner's decision
    assert out["financialHealth"] == "Not analysed"


def test_market_agent_switches_source_after_failure(monkeypatch):
    patch_data(monkeypatch, failing_sources=("marketstack",), fundamentals=FUNDAMENTALS,
               headlines=["x"])
    llm = FakeLLM({("MarketAnalyst", "ToolStep"): [
        {"thought": "try primary", "action": "get_price_history", "argument": "marketstack"},
        {"thought": "marketstack failed, use yfinance", "action": "get_price_history",
         "argument": "yfinance"},
        {"thought": "have prices", "action": "finish", "argument": ""}]})
    out = run_analysis(REQ, llm=llm)
    assert out["priceSource"] == "yfinance"
    assert out["sourcesTried"] == ["marketstack", "yfinance"]
    results = [e for e in events(out, "tool_result") if e["from"] == "tool:get_price_history"]
    assert [r["payload"]["ok"] for r in results] == [False, True]


def test_planner_replans_failed_analyst(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=None)  # every news source down
    retry = {"reasoning": "News failed; retry with company name", "action": "retry",
             "retries": [{"agent": "NewsAnalyst", "instruction": "search the company name"}],
             "confidence_cap": "Moderate"}
    llm = FakeLLM({("Planner", "Plan"): [PLAN], ("Planner", "Assessment"): [retry, PROCEED]})
    out = run_analysis(REQ, llm=llm)
    replans = events(out, "replan")
    assert replans and replans[0]["to"] == "NewsAnalyst"
    assert out["meta"]["replans"] == 1
    assert out["newsAvailable"] is False and out["recommendation"] in ("BUY", "HOLD", "SELL")


def test_no_price_data_fails_gracefully(monkeypatch):
    patch_data(monkeypatch, failing_sources=("marketstack", "alphavantage", "yfinance"))
    out = run_analysis(REQ, llm=FakeLLM(available=False))
    assert "error" in out and out["meta"]["status"] == "failed"
    assert events(out, "final")[-1]["payload"]["status"] == "failed"


def test_without_llm_every_agent_degrades_but_run_completes(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco profit rises"])
    out = run_analysis(REQ, llm=FakeLLM(available=False))
    assert out["meta"]["status"] == "degraded"
    assert "StrategyAgent" in out["meta"]["degradedAgents"]
    assert out["recommendation"] in ("BUY", "HOLD", "SELL")


def test_guardrail_overrides_llm_approval_of_unsuitable_buy(monkeypatch):
    # ~12% daily swings on a falling price: high risk for any investor
    volatile = [100 * 0.995 ** i * (1 + 0.06 * ((-1) ** i)) for i in range(120)]
    patch_data(monkeypatch, prices=volatile, fundamentals=FUNDAMENTALS, headlines=["x"])
    timid = AnalyzeRequest(ticker="TESTCO", age=70, riskAppetite="Conservative",
                           timeHorizon="Short-term").model_dump()
    llm = FakeLLM({("StrategyAgent", "StrategyDraft"): [BUY, HOLD],
                   ("RiskManager", "Critique"): [APPROVE, APPROVE]})
    out = run_analysis(timid, llm=llm)
    first = out["debate"][0]["critique"]
    assert first["verdict"] == "veto" and first["objections"][-1]["id"] == "G1"
    assert out["recommendation"] == "HOLD"


def test_memory_is_used_on_second_run(monkeypatch, tmp_path):
    from core.memory import RunMemory
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["x"])
    mem = RunMemory(str(tmp_path / "mem.db"))
    run_analysis(REQ, user_key="a@b.c", llm=FakeLLM(available=False), memory=mem)
    llm = FakeLLM({("Planner", "Plan"): [PLAN]})
    out = run_analysis(REQ, user_key="a@b.c", llm=llm, memory=mem)
    assert out["lastRun"] is not None and events(out, "memory")
    plan_prompt = [p for a, s, p in llm.calls if s == "Plan"][0]
    assert "Previous analysis of TESTCO" in plan_prompt


def test_trace_is_message_level_and_persisted(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["x"])
    out = run_analysis(REQ, llm=FakeLLM(available=False))
    from core.tracer import load_run
    saved = load_run(out["meta"]["runId"])
    assert len(saved) == len(out["trace"]) > 20
    assert [e["seq"] for e in saved] == list(range(1, len(saved) + 1))
    assert {"request", "plan", "task", "tool_call", "tool_result", "result", "draft",
            "critique", "final"} <= {e["type"] for e in saved}
