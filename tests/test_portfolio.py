import io

import pytest

from tools.base import ToolError
from tools.portfolio_analyzer import PortfolioAnalyzer, live_quote
from tests.fakes import patch_data, price_series, FUNDAMENTALS

CSV = b"ticker,quantity,buy_price\nAAA,10,100\nBBB,5,200\nZZZ,2,50\n"


def fake_quote(ticker):
    if ticker == "ZZZ":
        raise ToolError("no data")
    return {"AAA": {"price": 150.0, "volatility": 1.2, "source": "yfinance", "pe": 18.0, "sector": None},
            "BBB": {"price": 180.0, "volatility": 3.4, "source": "alphavantage", "pe": 40.0, "sector": "IT"}}[ticker]


def analyse(csv=CSV, **kw):
    return PortfolioAnalyzer(quote_fn=fake_quote, **kw).analyze_portfolio(io.BytesIO(csv), "h.csv")


def test_holdings_are_valued_at_live_prices():
    out = analyse()
    by = {s["ticker"]: s for s in out["stocks"]}
    assert by["AAA"]["currentPrice"] == 150.0 and by["AAA"]["priceSource"] == "live (yfinance)"
    assert by["AAA"]["pnl"] == 500.0
    assert out["livePriced"] == 2


def test_missing_quote_is_flagged_not_invented():
    by = {s["ticker"]: s for s in analyse()["stocks"]}
    assert by["ZZZ"]["currentPrice"] == 50.0
    assert by["ZZZ"]["priceSource"].startswith("unavailable")


def test_volatility_comes_from_price_history():
    by = {s["ticker"]: s for s in analyse()["stocks"]}
    assert by["BBB"]["isHighVol"] is True and by["AAA"]["isHighVol"] is False
    assert by["BBB"]["sector"] == "IT"


def test_quote_progress_is_reported():
    seen = []
    analyse(on_quote=lambda t, q, err: seen.append((t, err is None)))
    assert sorted(seen) == [("AAA", True), ("BBB", True), ("ZZZ", False)]


def test_live_quote_tries_sources_in_order(monkeypatch):
    patch_data(monkeypatch, failing_sources=("yfinance",), fundamentals=FUNDAMENTALS)
    q = live_quote("TESTCO")
    assert q["source"] == "alphavantage" and q["pe"] == 20.0


def test_live_quote_fails_cleanly(monkeypatch):
    patch_data(monkeypatch, failing_sources=("yfinance", "alphavantage", "marketstack"))
    with pytest.raises(ToolError):
        live_quote("TESTCO")


def test_no_static_price_table_left():
    import tools.portfolio_analyzer as pa
    assert not hasattr(pa, "PRICES") and not hasattr(pa, "PE_DATA")


def test_exchange_suffixes_and_lower_case_are_normalised():
    from tools.portfolio_analyzer import _norm_ticker
    assert [_norm_ticker(t) for t in ["tcs.ns", " INFY.BO", "ITC-EQ", "lt"]] == ["TCS", "INFY", "ITC", "LT"]


def test_rows_without_quantity_or_price_are_reported_not_silently_dropped():
    import io
    from tools.portfolio_analyzer import PortfolioAnalyzer
    csv = b"ticker,quantity,buy_price\nTCS,5,3500\nITC,0,430\nRELIANCE,15,\n"
    quote = lambda t: {"price": 100.0, "volatility": 1.5, "source": "yfinance", "trend": "Sideways",
                       "rsi": 50, "pe": 20, "sector": None, "history": []}
    out = PortfolioAnalyzer(quote_fn=quote).analyze_portfolio(io.BytesIO(csv), "p.csv")
    assert [s["ticker"] for s in out["stocks"]] == ["TCS"]
    assert out["skippedRows"] == ["ITC: quantity is 0 or missing", "RELIANCE: buy price is missing"]


def test_blank_excel_cells_never_become_nan():
    import math
    from tools.portfolio_analyzer import _safe_float
    assert _safe_float(float("nan")) == 0.0 and _safe_float(float("inf"), 1.0) == 1.0
    assert _safe_float("1,250.50") == 1250.5 and _safe_float(None) == 0.0 and not math.isnan(_safe_float("x"))


def test_zerodha_export_with_blank_price_cells_returns_valid_json(monkeypatch):
    import io, json
    from openpyxl import Workbook
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", False)
    import app as app_module
    from tools import portfolio_analyzer
    from tools.base import ToolError
    monkeypatch.setattr(portfolio_analyzer, "live_quote", lambda t: (_ for _ in ()).throw(ToolError("offline")))
    wb = Workbook(); ws = wb.active; ws.title = "Equity"
    ws.append([None, "Holdings statement"]); ws.append([])
    ws.append([None, "Symbol", "ISIN", "Sector", "Quantity Available", "Average Price",
               "Previous Closing Price", "Unrealized P&L", "Unrealized P&L Pct."])
    ws.append([None, "TCS", "INE467B01029", "IT", 5, 3300.0, None, None, None])
    ws.append([None, "NIFTYBEES", "INF204KB14I2", "ETF", 50, 260.0, None, None, None])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    app_module.init_db()
    client = app_module.app.test_client()
    res = client.post("/upload_portfolio", data={"file": (buf, "holdings.xlsx")},
                      content_type="multipart/form-data")
    body = res.get_data(as_text=True)
    assert res.status_code == 200 and "NaN" not in body
    assert {s["ticker"] for s in json.loads(body)["stocks"]} == {"TCS", "NIFTYBEES"}
