from agents.strategy_agent import StrategyAgent
from tests.agent_helpers import make_ctx, market, profile, risk


def state(**kw):
    s = {"market": market(), "profile": profile(), "risk": risk(score=12, gap=-15),
         "news": {"sentimentScore": 1, "newsSentiment": "Positive"},
         "fundamentals": {"healthScore": 80}, "confidenceCap": "High", "focus": "test"}
    s.update(kw)
    return s


def test_rules_buy_low_risk_and_targets_follow(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    out = StrategyAgent().propose(ctx, state(), 1, None, None)
    assert out["recommendation"] == "BUY" and out["targetPrice1"] > 100 > out["stopLoss"]


def test_vetoed_buy_is_downgraded_by_rules(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    veto = {"verdict": "veto", "objections": [{"id": "R1", "text": "x", "severity": "blocking"}]}
    out = StrategyAgent().propose(ctx, state(), 2, veto, {"recommendation": "BUY"})
    assert out["recommendation"] != "BUY"
    assert out["responses"][0]["objection_id"] == "R1"


def test_llm_answers_objections_and_confidence_is_capped(tmp_path):
    ctx, llm = make_ctx(tmp_path, {("StrategyAgent", "StrategyDraft"): [{
        "recommendation": "HOLD", "confidence": "High", "rationale": ["volatile"],
        "responses": [{"objection_id": "R1", "response": "Agreed, HOLD."}]}]})
    crit = {"verdict": "revise", "objections": [{"id": "R1", "text": "too risky",
                                                 "severity": "major"}]}
    out = StrategyAgent().propose(ctx, state(confidenceCap="Moderate"), 2, crit,
                                  {"recommendation": "BUY"})
    assert out["recommendation"] == "HOLD" and out["confidence"] == "Moderate"
    assert "too risky" in llm.calls[0][2]
