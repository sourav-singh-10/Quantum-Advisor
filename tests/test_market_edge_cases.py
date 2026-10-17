"""Cases taken from the shape of real NSE data: rebounds, slow declines and mixed news."""
from agents.strategy_agent import StrategyAgent
from tests.agent_helpers import make_ctx, market
from tests.test_strategy_agent import state
from tools.indicators import compute_indicators
from tools.news_data import keyword_sentiment


# Last 60 NSE closes recorded on 16 Oct 2026 (Yahoo Finance daily chart).
TCS_OCT26 = [2242.9, 2254.3, 2295.6, 2398, 2446.6, 2431.8, 2365.6, 2473.7, 2460, 2413, 2373, 2452.7, 2425.7, 2445.7, 2349.7, 2375, 2361, 2313.2, 2280, 2289, 2298, 2302, 2284.1, 2296.2, 2270, 2248.4, 2342, 2399.3, 2369, 2348, 2320.1, 2304, 2270, 2255.5, 2208, 2204.1, 2200.8, 2251, 2188.8, 2190, 2105, 2128.7, 2105, 2089.6, 2087, 2082, 2070.7, 2032.4, 2050.6, 2075, 2114.4, 2100, 2080.3, 2076, 2156, 2125, 2269.3, 2304.9, 2350, 2465]
RELIANCE_OCT26 = [1272.2, 1278, 1280, 1267.7, 1275.9, 1292.9, 1307.8, 1319, 1290.9, 1280, 1325, 1334.8, 1327.3, 1323.9, 1329, 1317, 1310, 1316, 1322, 1311, 1313.2, 1316, 1309.8, 1317, 1298, 1282.2, 1287, 1277, 1309, 1313.1, 1302.5, 1322, 1309.5, 1294.9, 1279, 1274, 1257.5, 1235.3, 1240, 1243.9, 1226.4, 1247.4, 1240.4, 1248, 1219.2, 1226, 1197.6, 1182, 1187, 1167.7, 1186.4, 1218, 1207.7, 1178, 1170.3, 1158.9, 1166.7, 1174.6, 1215, 1211.2]


def test_sharp_rebound_above_both_averages_is_not_downtrend():
    # TCS: down for months, then about 15% above its 20-day average in one week.
    ind = compute_indicators(TCS_OCT26)
    assert ind["ma20"] < ind["ma50"]          # the cross-only rule called this Downtrend
    assert ind["trend"] == "Uptrend"


def test_small_bounce_inside_a_decline_is_still_downtrend():
    # RELIANCE: a 1% bounce over the 20-day average while well under the 50-day.
    ind = compute_indicators(RELIANCE_OCT26)
    assert ind["currentPrice"] < ind["ma50"]
    assert ind["trend"] == "Downtrend"


def test_flat_averages_are_sideways():
    ind = compute_indicators([700 + (i % 5) for i in range(120)])
    assert ind["trend"] == "Sideways"


def test_near_tie_in_headlines_is_neutral():
    titles = ["Shares surge on index rally", "Regulator seizes assets, warns of risk"]
    assert keyword_sentiment(titles)["newsSentiment"] == "Neutral"


def test_clear_majority_still_counts():
    titles = ["Profit beats estimates", "Dividend declared, shares surge", "Record growth"]
    assert keyword_sentiment(titles)["sentimentScore"] == 1


def test_rules_do_not_buy_into_a_downtrend(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    s = state(market={**market(), "trend": "Downtrend"})
    out = StrategyAgent().propose(ctx, s, 1, None, None)
    assert out["recommendation"] == "HOLD"


def test_sixty_year_old_counts_as_older_investor():
    from tools.risk_rules import risk_capacity
    base = {"experience": "Experienced", "riskAppetite": "Conservative", "timeHorizon": "Short-term"}
    assert risk_capacity({**base, "age": 60}) == risk_capacity({**base, "age": 70}) == 25
    assert risk_capacity({**base, "age": 55}) == 35


def test_risk_manager_objects_to_buying_when_strongly_overbought(tmp_path):
    from agents.risk_agent import RiskManager
    ctx, _ = make_ctx(tmp_path, available=False)
    s = state(market={**market(), "rsi": 81})
    s["risk"] = {**s["risk"], "riskFactors": [], "keyRisks": []}
    crit = RiskManager().review(ctx, {"recommendation": "BUY", "confidence": "Moderate"}, s, 1, [])
    assert crit.verdict == "revise" and crit.objections[0].id == "R3"
    out = StrategyAgent().propose(ctx, s, 2, crit.model_dump(), {"recommendation": "BUY"})
    assert out["recommendation"] == "HOLD"


def test_portfolio_calls_agree_with_trend_and_rsi():
    from tools.portfolio_analyzer import PortfolioAnalyzer
    quotes = {"FALLING": {"price": 90, "volatility": 1.3, "source": "yfinance", "trend": "Downtrend",
                          "rsi": 45, "pe": 20, "sector": "Energy"},
              "HOT": {"price": 95, "volatility": 1.5, "source": "yfinance", "trend": "Uptrend",
                      "rsi": 81, "pe": 17, "sector": "IT"},
              "CALM": {"price": 95, "volatility": 1.2, "source": "yfinance", "trend": "Sideways",
                       "rsi": 50, "pe": 15, "sector": "Banking"}}

    def quote(t):
        if t not in quotes:
            from tools.base import ToolError
            raise ToolError("no data")
        return quotes[t]

    import io
    csv = "ticker,quantity,buy_price\n" + "".join(f"{t},10,100\n" for t in [*quotes, "ZOMATO"])
    out = PortfolioAnalyzer(quote_fn=quote).analyze_portfolio(io.BytesIO(csv.encode()), "h.csv")
    calls = {s["ticker"]: (s["recommendation"], s["reason"]) for s in out["stocks"]}
    assert calls["FALLING"][0] == "HOLD" and "falling" in calls["FALLING"][1]
    assert calls["HOT"][0] == "HOLD" and "Overbought" in calls["HOT"][1]
    assert calls["CALM"][0] == "BUY"
    assert calls["ZOMATO"][0] == "REVIEW" and "ETERNAL" in calls["ZOMATO"][1]
    notes = {r["ticker"]: r["note"] for r in out["recommendations"]}
    assert notes["HOT"] == calls["HOT"][1]


def test_volume_signal_compares_recent_volume_with_its_average():
    import time
    from tools import base
    from tools.market_data import volume_signal
    with base._cache_lock:
        base._cache[("volume", "VOLCO")] = (time.time(), [1000.0] * 60 + [2500.0] * 5)
    out = volume_signal("VOLCO")
    assert out["volumeLevel"] == "High" and out["volumeRatio"] > 1.5


def test_volume_signal_needs_yfinance_data():
    import pytest
    from tools.base import ToolError
    from tools.market_data import volume_signal
    with pytest.raises(ToolError):
        volume_signal("NOVOL")


def test_merged_symbol_is_analysed_under_its_new_name(monkeypatch):
    from core.runner import run_analysis
    from core.schemas import AnalyzeRequest
    from tests.fakes import FUNDAMENTALS, FakeLLM, patch_data
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["x"])
    out = run_analysis(AnalyzeRequest(ticker="HDFC").model_dump(), llm=FakeLLM(available=False))
    assert out["ticker"] == "HDFCBANK" and out["requestedTicker"] == "HDFC"
    assert any(e["type"] == "decision" and "HDFCBANK" in str(e["payload"]) for e in out["trace"])


def test_market_analyst_can_switch_symbol_when_told(monkeypatch, tmp_path):
    from agents.market_agent import MarketAnalyst
    from tests.fakes import price_series
    from tools import market_data
    from tools.base import ToolError

    def only_newco(symbol):
        if symbol != "NEWCO":
            raise ToolError(f"no rows for {symbol}")
        return price_series()
    monkeypatch.setitem(market_data._FETCHERS, "yfinance", only_newco)
    steps = [{"thought": "old symbol", "action": "get_price_history", "argument": "yfinance"},
             {"thought": "the Planner says it trades as NEWCO", "action": "get_price_history",
              "argument": "yfinance:NEWCO"}]
    ctx, _ = make_ctx(tmp_path, {("MarketAnalyst", "ToolStep"): steps})
    out = MarketAnalyst().run(ctx, "OLDCO", "Use the symbol NEWCO instead")
    assert out["ticker"] == "NEWCO" and out["priceSource"] == "yfinance"


def test_risk_breakdown_adds_up_to_the_score():
    from tools.risk_rules import market_risk_score
    out = market_risk_score({"volatility": 2.2, "rsi": 81, "trend": "Uptrend", "change1mPct": 12.6,
                             "maxDrawdownPct": -24}, {"healthScore": 85}, {"sentimentScore": 1})
    assert sum(p["points"] for p in out["riskBreakdown"]) == out["riskScore"] == 29
    assert {p["label"] for p in out["riskBreakdown"]} >= {"Volatility", "Momentum", "Trend"}


def test_every_headline_gets_a_label_without_the_llm(monkeypatch, tmp_path):
    from agents.news_agent import NewsAnalyst
    from tests.fakes import patch_data
    patch_data(monkeypatch, headlines=["Profit beats estimates, record growth", "Shares plunge after probe",
                                       "Company holds annual meeting"])
    ctx, _ = make_ctx(tmp_path, available=False)
    out = NewsAnalyst().run(ctx, "TESTCO")
    assert [h["sentiment"] for h in out["headlineLabels"]] == ["Positive", "Negative", "Neutral"]


def test_sample_portfolio_is_served_and_parses(monkeypatch):
    import io
    from pathlib import Path
    from tools.portfolio_analyzer import PortfolioAnalyzer
    csv = (Path(__file__).resolve().parents[1] / "frontend/samples/sample_portfolio.csv").read_bytes()
    quote = lambda t: {"price": 100.0, "volatility": 1.5, "source": "yfinance", "trend": "Sideways",
                       "rsi": 50, "pe": 20, "sector": None, "history": [99.0, 100.0]}
    out = PortfolioAnalyzer(quote_fn=quote).analyze_portfolio(io.BytesIO(csv), "sample.csv")
    assert len(out["stocks"]) == 8 and abs(sum(s["weight"] for s in out["stocks"]) - 100) < 0.5
    assert out["stocks"][0]["history"] == [99.0, 100.0]
