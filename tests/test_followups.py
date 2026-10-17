"""Agents asking each other for more evidence: Strategy or Risk -> Planner -> an analyst -> answer."""
import pytest

from core.runner import run_analysis
from core.schemas import AnalyzeRequest
from tests.fakes import FUNDAMENTALS, FakeLLM, patch_data, price_series
from tests.test_agent_paths import APPROVE, BUY, HOLD, PLAN, PROCEED, REVISE, events

REQ = AnalyzeRequest(ticker="TESTCO").model_dump()


@pytest.fixture(autouse=True)
def year_of_prices(monkeypatch):
    from tools import market_snapshot
    closes = price_series(250, start=80, drift=0.002)
    monkeypatch.setattr(market_snapshot, "_yf_year", lambda s: (closes, [1.0] * 250, [f"d{i}" for i in range(250)]))


ASK_NEWS = {**REVISE, "followup": {"agent": "NewsAnalyst",
                                   "question": "Is the probe headline about Testco itself?",
                                   "why": "A probe would change the risk."}}
GRANT = {"grant": True, "agent": "NewsAnalyst",
         "instruction": "Check whether the probe headline names Testco", "reasoning": "Material."}
ANSWER = {"answer": "No: the probe concerns a different company; Testco is not named.",
          "evidence": ["Headline names OtherCo"], "changes_view": True}


def test_risk_manager_asks_planner_routes_analyst_answers_and_debate_continues(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco wins order", "OtherCo faces probe"])
    llm = FakeLLM({("Planner", "Plan"): [PLAN], ("Planner", "Assessment"): [PROCEED],
                   ("StrategyAgent", "StrategyDraft"): [BUY, HOLD],
                   ("RiskManager", "Critique"): [ASK_NEWS, APPROVE],
                   ("Planner", "FollowUpGrant"): [GRANT],
                   ("NewsAnalyst", "FollowUpAnswer"): [ANSWER]})
    out = run_analysis(REQ, llm=llm)
    seq = [(e["from"], e["to"], e["type"]) for e in out["trace"]
           if e["type"] in ("followup", "decision", "task", "answer") and e["from"] != "MarketAnalyst"]
    i = seq.index(("RiskManager", "Planner", "followup"))
    assert seq[i + 1] == ("Planner", "RiskManager", "decision")
    assert seq[i + 2] == ("Planner", "NewsAnalyst", "task")
    assert seq[i + 3] == ("NewsAnalyst", "RiskManager", "answer")
    # the strategist's next draft saw the answer
    round2 = [p for a, s, p in llm.calls if a == "StrategyAgent"][1]
    assert "Testco is not named" in round2 and "changes the earlier view" in round2
    assert out["followups"][0]["granted"] and out["meta"]["followups"] == 1
    assert out["decidedBy"] == "Risk approved in round 2"


def test_strategist_can_ask_before_committing_and_redrafts_the_same_round(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco wins order"])
    asking = {**BUY, "followup": {"agent": "MarketAnalyst", "question": "How does the last year look?",
                                  "why": "Three months may hide a decline."}}
    grant = {**GRANT, "agent": "MarketAnalyst", "instruction": "One-year view"}
    llm = FakeLLM({("Planner", "Plan"): [PLAN], ("Planner", "Assessment"): [PROCEED],
                   ("StrategyAgent", "StrategyDraft"): [asking, BUY],
                   ("RiskManager", "Critique"): [APPROVE],
                   ("Planner", "FollowUpGrant"): [grant]})
    out = run_analysis(REQ, llm=llm)
    assert [d["round"] for d in events(out, "draft")] == [1, 1]
    ans = events(out, "answer")[0]
    assert ans["from"] == "MarketAnalyst" and ans["to"] == "StrategyAgent"
    assert "one year" in ans["payload"]["answer"].lower() or "last year" in ans["payload"]["answer"].lower()
    assert any(e["payload"].get("argument", "").endswith("1y") for e in events(out, "tool_call"))
    assert out["decidedBy"] == "Risk approved in round 1"


def test_planner_will_not_route_to_an_analyst_that_is_not_in_the_run(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco wins order"])
    ask_doc = {**REVISE, "followup": {"agent": "DocumentAnalyst", "question": "What do the notes say?"}}
    llm = FakeLLM({("Planner", "Plan"): [PLAN], ("Planner", "Assessment"): [PROCEED],
                   ("StrategyAgent", "StrategyDraft"): [BUY, HOLD],
                   ("RiskManager", "Critique"): [ask_doc, APPROVE]})
    out = run_analysis(REQ, llm=llm)
    assert out["followups"] == [] and not events(out, "followup")   # dropped: no document attached


def test_follow_ups_are_limited(monkeypatch):
    import config
    monkeypatch.setattr(config, "MAX_FOLLOWUPS", 1)
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco wins order"])
    llm = FakeLLM({("Planner", "Plan"): [PLAN], ("Planner", "Assessment"): [PROCEED],
                   ("StrategyAgent", "StrategyDraft"): [BUY, BUY, HOLD],
                   ("RiskManager", "Critique"): [ASK_NEWS, ASK_NEWS, APPROVE],
                   ("Planner", "FollowUpGrant"): [GRANT, GRANT]})
    out = run_analysis(REQ, llm=llm)
    assert len(out["followups"]) == 1
    second_review = [p for a, s, p in llm.calls if a == "RiskManager" and "Round 2" in p][0]
    assert "No more follow-up questions are allowed" in second_review


def test_rules_alone_ask_for_a_longer_view_before_backing_a_buy_after_a_sharp_rise(monkeypatch):
    # No LLM: the rule fallback still runs the follow-up loop end to end.
    rising = [100 * (1.01 ** i) for i in range(100)]
    patch_data(monkeypatch, prices=rising, fundamentals={**FUNDAMENTALS, "roe": 30.0},
               headlines=["Testco profit beats estimates, record growth"])
    out = run_analysis(AnalyzeRequest(ticker="TESTCO", age=25, riskAppetite="Aggressive",
                                      timeHorizon="Long-term").model_dump(),
                       llm=FakeLLM(available=False))
    assert out["debate"][0]["draft"]["recommendation"] == "BUY"
    assert out["followups"] and out["followups"][0]["agent"] == "MarketAnalyst"
    assert "Over the last year" in events(out, "answer")[0]["payload"]["answer"]
    assert events(out, "answer")[0]["to"] == "RiskManager" and len(out["debate"]) == 2
