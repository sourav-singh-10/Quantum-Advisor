
from unittest.mock import Mock, patch

import pytest

from agents.market_agent import MarketAgent


@patch("agents.market_agent.requests.get")
def test_marketstack_success(mock_get):
    response = Mock()
    response.json.return_value = {
        "data": [
            {"close": 100},
            {"close": 110},
        ]
    }
    mock_get.return_value = response

    agent = MarketAgent()
    prices = agent.get_marketstack_history("RELIANCE")

    assert prices == [110, 100]


@patch("agents.market_agent.requests.get")
def test_alpha_vantage_fallback(mock_get):
    marketstack_response = Mock()
    marketstack_response.json.return_value = {}

    alpha_response = Mock()
    alpha_response.json.return_value = {
        "Time Series (Daily)": {
            "2026-10-10": {"4. close": "120"},
            "2026-10-09": {"4. close": "110"},
        }
    }

    mock_get.side_effect = [
        marketstack_response,
        alpha_response,
    ]

    agent = MarketAgent()
    result = agent.analyze("reliance")

    assert result["ticker"] == "RELIANCE"
    assert result["priceSource"] == "AlphaVantage"
    assert result["currentPrice"] == 120.0
    assert mock_get.call_count == 2


@patch("agents.market_agent.requests.get")
def test_both_apis_fail(mock_get):
    response = Mock()
    response.json.return_value = {}
    mock_get.return_value = response

    agent = MarketAgent()

    with pytest.raises(Exception, match="No data from any API"):
        agent.analyze("RELIANCE")

    assert mock_get.call_count == 2
