from agents.risk_agent import RiskManager
from tests.agent_helpers import make_ctx, market, profile, risk

BUY = {"recommendation": "BUY", "confidence": "High", "rationale": [], "responses": []}


def state(**kw):
    s = {"market": market(), "profile": profile(), "risk": risk(), "confidenceCap": "High"}
    s.update(kw)
    return s


def test_assess_uses_investor_capacity(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    calm = RiskManager().assess(ctx, state(profile=profile(capacity=90)))
    timid = RiskManager().assess(ctx, state(profile=profile(capacity=5)))
    assert calm["riskScore"] == timid["riskScore"]
    assert timid["suitabilityGap"] > calm["suitabilityGap"]


def test_rule_review_asks_revision_for_unsuitable_buy(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    c = RiskManager().review(ctx, BUY, state(risk=risk(score=27, gap=4)), 1, [])
    assert c.verdict == "revise" and c.objections[0].id == "R1"


def test_rule_review_vetoes_high_risk_buy(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    c = RiskManager().review(ctx, BUY, state(risk=risk(score=40, level="High", gap=12)), 1, [])
    assert c.verdict == "veto"


def test_confidence_above_data_quality_is_challenged(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    hold = {**BUY, "recommendation": "HOLD"}
    c = RiskManager().review(ctx, hold, state(confidenceCap="Low"), 1, [])
    assert [o.id for o in c.objections] == ["R2"]


def test_guardrail_overrides_llm_approval(tmp_path):
    ctx, _ = make_ctx(tmp_path, {("RiskManager", "Critique"): [
        {"verdict": "approve", "reasoning": "looks fine", "objections": []}]})
    c = RiskManager().review(ctx, BUY, state(risk=risk(score=45, level="High", gap=20)), 1, [])
    assert c.verdict == "veto" and c.objections[-1].id == "G1"


def test_review_sees_earlier_rounds(tmp_path):
    ctx, llm = make_ctx(tmp_path, {("RiskManager", "Critique"): [
        {"verdict": "approve", "reasoning": "R1 resolved", "objections": []}]})
    history = [{"round": 1, "draft": BUY, "critique": {"verdict": "revise", "objections": [
        {"id": "R1", "text": "too volatile", "severity": "major"}]}}]
    RiskManager().review(ctx, {**BUY, "recommendation": "HOLD"}, state(), 2, history)
    assert "R1: too volatile" in llm.calls[0][2]
