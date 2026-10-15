from agents.portfolio_agent import PortfolioAgent
from agents.report_agent import ReportAgent
from tests.agent_helpers import make_ctx, market, profile, risk

FINAL = {"recommendation": "HOLD", "confidence": "Moderate", "targetPrice1": 110,
         "targetPrice2": 120, "stopLoss": 90, "rationale": ["x"], "decidedBy": "Risk approved"}


def test_portfolio_never_says_buy_on_hold(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    out = PortfolioAgent().run(ctx, {"market": market(), "profile": profile(), "final": FINAL},
                               {"portfolioValue": 200000})
    assert out["positionSizing"]["units"] == 0
    assert not any("Buy" in line for line in out["portfolioAdvice"])


def test_portfolio_sizes_from_real_portfolio_value(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    buy = {**FINAL, "recommendation": "BUY"}
    small = PortfolioAgent().run(ctx, {"market": market(), "profile": profile(), "final": buy},
                                 {"portfolioValue": 20000})
    large = PortfolioAgent().run(ctx, {"market": market(), "profile": profile(), "final": buy},
                                 {"portfolioValue": 2000000})
    assert large["positionSizing"]["units"] > small["positionSizing"]["units"]


def test_report_mentions_the_debate(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    st = {"market": market(), "risk": risk(), "final": FINAL,
          "debate": [{"round": 1, "critique": {"verdict": "revise", "objections": [
              {"id": "R1", "text": "too volatile", "severity": "major"}]}},
                     {"round": 2, "critique": {"verdict": "approve", "objections": []}}],
          "portfolio": {"portfolioAdvice": []}}
    text = ReportAgent().run(ctx, st)["aiReport"]
    assert "too volatile" in text and "HOLD" in text
