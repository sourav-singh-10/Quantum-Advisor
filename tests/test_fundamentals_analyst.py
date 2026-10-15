from agents.fundamentals_agent import FundamentalsAnalyst
from tests.agent_helpers import make_ctx
from tests.fakes import FUNDAMENTALS, patch_data


def test_uses_llm_view_with_real_ratios(monkeypatch, tmp_path):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS)
    ctx, llm = make_ctx(tmp_path, {("FundamentalsAnalyst", "FundamentalsView"): [
        {"summary": "Healthy", "financialHealth": "Strong", "key_points": ["ROE 18%"]}]})
    out = FundamentalsAnalyst().run(ctx, "TESTCO", "focus on debt")
    assert out["financialHealth"] == "Strong" and out["roe"] == 18.0
    assert "focus on debt" in llm.calls[0][2]


def test_missing_data_is_reported_not_invented(monkeypatch, tmp_path):
    patch_data(monkeypatch, fundamentals=None)
    ctx, _ = make_ctx(tmp_path)
    out = FundamentalsAnalyst().run(ctx, "TESTCO")
    assert out["fundamentalsAvailable"] is False and out["healthScore"] is None
