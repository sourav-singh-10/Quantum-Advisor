from agents.profile_agent import ProfileAgent
from core.schemas import AnalyzeRequest
from tests.agent_helpers import make_ctx


def test_goal_becomes_constraints(tmp_path):
    ctx, llm = make_ctx(tmp_path, {("ProfileAgent", "ProfileView"): [{
        "summary": "Saver with a fixed date", "max_position_pct": 40, "horizon_years": 3,
        "constraints": ["needs the money in 3 years"]}]})
    req = AnalyzeRequest(ticker="TCS", goal="House down-payment in 3 years").model_dump()
    out = ProfileAgent().run(ctx, req)
    assert out["constraints"] == ["needs the money in 3 years"]
    assert out["maxPositionPct"] == 15        # clamped: never more than 15% in one stock
    assert "House down-payment" in llm.calls[0][2]


def test_rules_without_llm(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    out = ProfileAgent().run(ctx, AnalyzeRequest(ticker="TCS", age=65).model_dump())
    assert out["riskCapacityScore"] == 25 and 5 <= out["maxPositionPct"] <= 15
