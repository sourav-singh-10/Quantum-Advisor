"""Shared builders for agent unit tests."""
from core.context import RunContext
from core.tracer import Tracer
from tests.fakes import FakeLLM


def make_ctx(tmp_path, script=None, available=True):
    llm = FakeLLM(script, available=available)
    return RunContext(llm=llm, tracer=Tracer(log_dir=tmp_path)), llm


def market(**kw):
    base = {"ticker": "TESTCO", "currentPrice": 100.0, "priceDisplay": "₹100.00", "rsi": 50.0,
            "volatility": 1.5, "trend": "Uptrend", "change1mPct": 3.0, "observations": 120,
            "marketSummary": "steady uptrend"}
    return {**base, **kw}


def profile(capacity=55, max_pct=8.0):
    return {"riskCapacityScore": capacity, "profileSummary": "Test investor.",
            "maxPositionPct": max_pct, "constraints": [], "horizonYears": 3}


def risk(score=20, level="Medium", gap=-5):
    return {"riskScore": score, "riskLevel": level, "riskFactors": [], "suitabilityGap": gap,
            "riskSummary": "test", "keyRisks": []}
