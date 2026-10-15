import pytest
from pydantic import ValidationError

from core.schemas import AnalyzeRequest, Critique, StrategyDraft


def test_ticker_is_normalised():
    assert AnalyzeRequest(ticker=" reliance.ns ").ticker == "RELIANCE"
    assert AnalyzeRequest(ticker="M&M").ticker == "M&M"


@pytest.mark.parametrize("bad", [{"ticker": ""}, {"ticker": "DROP TABLE;"},
                                 {"ticker": "TCS", "age": 12},
                                 {"ticker": "TCS", "portfolioValue": 0},
                                 {"ticker": "TCS", "timeHorizon": "Forever"},
                                 {"ticker": "TCS", "goal": "x" * 301}])
def test_bad_requests_are_rejected(bad):
    with pytest.raises(ValidationError):
        AnalyzeRequest(**bad)


def test_llm_schemas_restrict_choices():
    with pytest.raises(ValidationError):
        Critique(verdict="maybe", reasoning="", objections=[])
    with pytest.raises(ValidationError):
        StrategyDraft(recommendation="STRONG BUY", confidence="High", rationale=[])
