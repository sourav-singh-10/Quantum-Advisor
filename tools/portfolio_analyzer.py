"""
PortfolioAnalyzer — handles two input formats:

FORMAT A — Simple CSV/XLSX (user-created):
    ticker, quantity, buy_price
    RELIANCE, 10, 2400

FORMAT B — Zerodha Holdings Export (XLSX):
    Multi-sheet file (Equity / Mutual Funds / Combined) with many header
    rows and Zerodha-specific columns:
    Symbol | ISIN | Sector | Quantity Available | Average Price | Previous Closing Price | ...
    The actual data starts after a row whose col[1] == "Symbol".
    Col[0] is always NaN (first column is blank in Zerodha exports).
"""

import csv
import io
import math
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from tools import fundamentals_data, market_data
from tools.base import ToolError
from tools.indicators import compute_indicators

MAX_LIVE_QUOTES = 30          # free data sources are rate-limited
HIGH_VOL_DAILY_PCT = 2.5      # daily volatility above this counts as high

# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR NAMES (metadata only; prices and ratios are fetched live)
# ─────────────────────────────────────────────────────────────────────────────
SECTORS = {
    "IOC": "Oil & Gas", "BPCL": "Oil & Gas", "ONGC": "Oil & Gas",
    "GAIL": "Oil & Gas", "PETRONET": "Oil & Gas", "HINDPETRO": "Oil & Gas",
    "RELIANCE": "Oil & Gas",
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking",
    "AXISBANK": "Banking", "KOTAKBANK": "Banking", "INDUSINDBK": "Banking",
    "BANDHANBNK": "Banking", "FEDERALBNK": "Banking", "PNB": "Banking",
    "CANBK": "Banking", "UNIONBANK": "Banking", "BANKBARODA": "Banking",
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT",
    "TECHM": "IT", "LTI": "IT", "LTIM": "IT", "MPHASIS": "IT", "COFORGE": "IT",
    "MARUTI": "Auto", "TATAMOTORS": "Auto", "MM": "Auto",
    "BAJAJAUTO": "Auto", "EICHERMOT": "Auto", "HEROMOTOCO": "Auto",
    "TVSMOTOR": "Auto", "HYUNDAI": "Auto",
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma",
    "DIVISLAB": "Pharma", "BIOCON": "Pharma", "AUROPHARMA": "Pharma", "LUPIN": "Pharma",
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "DABUR": "FMCG", "MARICO": "FMCG", "GODREJCP": "FMCG",
    "TATASTEEL": "Metals", "HINDALCO": "Metals", "JSWSTEEL": "Metals",
    "VEDL": "Metals", "NMDC": "Metals", "COALINDIA": "Metals", "SAIL": "Metals",
    "LT": "Infra", "ULTRACEMCO": "Infra", "GRASIM": "Infra",
    "ADANIPORTS": "Infra", "BHARTIARTL": "Telecom", "POWERGRID": "Utilities",
    "ADANIENT": "Infra",
    "DMART": "Retail", "TRENT": "Retail", "DLF": "Real Estate",
    "GODREJPROP": "Real Estate", "PRESTIGE": "Real Estate",
    "NTPC": "Utilities", "TATAPOWER": "Utilities", "ADANIGREEN": "Utilities",
    "TITAN": "Consumer", "VOLTAS": "Consumer", "HAVELLS": "Consumer", "CROMPTON": "Consumer",
    "BAJFINANCE": "Finance", "BAJAJFINSV": "Finance", "HDFCLIFE": "Finance",
    "SBILIFE": "Finance", "ICICIPRULI": "Finance",
    "ASIANPAINT": "Consumer", "ZOMATO": "Consumer", "PAYTM": "Finance",
    "NYKAA": "Consumer", "IRCTC": "Utilities",
    "GOLDBEES": "ETF", "GOLDBEES-E": "ETF", "NIFTYBEES": "ETF", "BANKBEES": "ETF",
}



RENAMED = market_data.RENAMED


def live_quote(ticker: str) -> dict:
    """Latest close, daily volatility and P/E for one NSE ticker, from the first free
    source that answers. Raises ToolError when no source has data."""
    errors = []
    for source in market_data.SOURCES:
        try:
            prices = market_data.get_price_history(ticker, source)
            ind = compute_indicators(prices)
            break
        except ToolError as exc:
            errors.append(f"{source}: {exc}")
    else:
        raise ToolError("; ".join(errors))
    quote = {"price": ind["currentPrice"], "volatility": ind["volatility"], "source": source,
             "trend": ind["trend"], "rsi": ind["rsi"], "pe": None, "sector": None,
             "history": [round(x, 2) for x in prices[-60:]]}
    try:
        f = fundamentals_data.fetch_fundamentals(ticker)
        quote["pe"], quote["sector"] = f.get("pe"), f.get("sector")
    except ToolError:
        pass
    return quote


def _safe_float(v, default=0.0):
    """float(v), or ``default`` for blanks, text, NaN and infinity (empty Excel cells are NaN)."""
    try:
        f = float(str(v).replace(",", "")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _norm_ticker(raw):
    """Upper-case and strip exchange suffixes people paste in: TCS.NS, TCS.BO, TCS-EQ."""
    t = str(raw).strip().upper()
    for suffix in (".NS", ".BO", ".NSE", ".BSE", "-EQ", "-BE"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    return t


# ─────────────────────────────────────────────────────────────────────────────
#  ZERODHA FORMAT DETECTOR & PARSER
# ─────────────────────────────────────────────────────────────────────────────
def _is_zerodha(df: pd.DataFrame) -> bool:
    """
    Zerodha exports have col[0] == NaN for every row, and somewhere
    in the sheet there's a row whose col[1] == 'Symbol'.
    """
    col1_vals = df.iloc[:, 1].astype(str).str.strip().tolist()
    return "Symbol" in col1_vals


def _parse_zerodha_sheet(df: pd.DataFrame):
    """
    Find the 'Symbol' header row, then read rows below it.
    Returns list of dicts: {ticker, quantity, buy_price, current_price,
                             sector, pnl, pnl_pct}
    Uses the values already in the file for current price + P&L.
    """
    col1_vals = df.iloc[:, 1].astype(str).str.strip().tolist()
    header_row_idx = col1_vals.index("Symbol")

    # Build a clean DataFrame from that row onwards
    sub = df.iloc[header_row_idx:].copy()
    sub.columns = [str(v).strip() if v is not None else f"_col{i}"
                   for i, v in enumerate(sub.iloc[0])]
    sub = sub.iloc[1:].reset_index(drop=True)   # drop the header row itself

    rows = []
    for _, row in sub.iterrows():
        ticker = _norm_ticker(row.get("Symbol", ""))
        if not ticker or ticker.lower() in ("nan", "symbol", ""):
            continue

        # Zerodha uses "Quantity Available" for how many you currently hold
        qty = _safe_float(
            row.get("Quantity Available",
            row.get("Quantity", 0))
        )
        if qty <= 0:
            continue

        buy_price     = _safe_float(row.get("Average Price", 0))
        current_price = _safe_float(row.get("Previous Closing Price", 0))
        pnl           = _safe_float(row.get("Unrealized P&L", 0))
        pnl_pct       = _safe_float(
            row.get("Unrealized P&L Pct.",
            row.get("Unrealize P&L Pct.", 0))
        )

        # Sector: use Zerodha's own value if present, fall back to our map
        zerodha_sector = str(row.get("Sector", "")).strip()
        sector = (
            SECTORS.get(ticker)
            or (zerodha_sector if zerodha_sector not in ("nan", "", "-") else None)
            or "Other"
        )

        rows.append({
            "ticker":        ticker,
            "quantity":      qty,
            "buy_price":     buy_price,
            "current_price": current_price,
            "sector":        sector,
            "pnl":           pnl,
            "pnl_pct":       pnl_pct,
        })

    return rows


# ─────────────────────────────────────────────────────────────────────────────
#  SIMPLE FORMAT PARSER  (ticker, quantity, buy_price)
# ─────────────────────────────────────────────────────────────────────────────
def _parse_simple_xlsx(file, skipped: list | None = None) -> list:
    df = pd.read_excel(file, header=None)
    # Find header row: look for a row containing 'ticker' or 'symbol'
    header_idx = 0
    for i, row in df.iterrows():
        vals = [str(v).strip().lower() for v in row if pd.notna(v)]
        if any(v in ("ticker", "symbol") for v in vals):
            header_idx = i
            break

    sub = df.iloc[header_idx:].copy()
    sub.columns = [str(v).strip().lower() if pd.notna(v) else f"_c{i}"
                   for i, v in enumerate(sub.iloc[0])]
    sub = sub.iloc[1:].reset_index(drop=True)

    rows = []
    for _, row in sub.iterrows():
        ticker = _norm_ticker(row.get("ticker", row.get("symbol", "")))
        if not ticker or ticker.lower() in ("nan", ""):
            continue
        qty       = _safe_float(row.get("quantity", row.get("qty", 0)))
        buy_price = _safe_float(row.get("buy_price", row.get("price", 0)))
        if qty <= 0 or buy_price <= 0:
            if skipped is not None:
                skipped.append(f"{ticker}: {'quantity is 0 or missing' if qty <= 0 else 'buy price is missing'}")
            continue
        rows.append({"ticker": ticker, "quantity": qty,
                     "buy_price": buy_price, "current_price": None,
                     "sector": None, "pnl": None, "pnl_pct": None})
    return rows


def _parse_simple_csv(file, skipped: list | None = None) -> list:
    text   = file.read().decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    rows   = []
    for r in reader:
        norm = {k.strip().lower(): v for k, v in r.items()}
        ticker    = _norm_ticker(norm.get("ticker", norm.get("symbol", "")))
        qty       = _safe_float(norm.get("quantity", norm.get("qty", 0)))
        buy_price = _safe_float(norm.get("buy_price", norm.get("price", 0)))
        if not ticker:
            continue
        if qty <= 0 or buy_price <= 0:
            if skipped is not None:
                skipped.append(f"{ticker}: {'quantity is 0 or missing' if qty <= 0 else 'buy price is missing'}")
            continue
        rows.append({"ticker": ticker, "quantity": qty,
                     "buy_price": buy_price, "current_price": None,
                     "sector": None, "pnl": None, "pnl_pct": None})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN ANALYZER CLASS
# ─────────────────────────────────────────────────────────────────────────────
class PortfolioAnalyzer:

    def __init__(self, quote_fn=None, on_quote=None):
        self.quote_fn = quote_fn or live_quote
        self.on_quote = on_quote          # optional callback(ticker, quote|None, error|None) for tracing

    def _quotes(self, tickers: list[str]) -> dict:
        unique = list(dict.fromkeys(tickers))[:MAX_LIVE_QUOTES]

        def one(t):
            try:
                q = self.quote_fn(t)
                if self.on_quote:
                    self.on_quote(t, q, None)
                return t, q
            except Exception as exc:          # one bad ticker must not stop the review
                if self.on_quote:
                    self.on_quote(t, None, str(exc))
                return t, None

        with ThreadPoolExecutor(max_workers=6) as pool:
            return dict(pool.map(one, unique))

    # ── Entry point ──────────────────────────────────────────────────────────
    def analyze_portfolio(self, file, filename: str):
        raw_rows = self._parse(file, filename)
        if not raw_rows:
            raise Exception(
                "No valid holdings found. "
                "Expected Zerodha Holdings Export (.xlsx) or a CSV with "
                "columns: ticker, quantity, buy_price"
            )
        result = self._build_analysis(raw_rows)
        result["skippedRows"] = list(getattr(self, "skipped", []))
        return result

    # ── Parse dispatcher ─────────────────────────────────────────────────────
    def _parse(self, file, filename: str):
        self.skipped = []
        if filename.endswith(".xlsx") or filename.endswith(".xlsm"):
            return self._parse_xlsx(file)
        elif filename.endswith(".csv"):
            return _parse_simple_csv(file, self.skipped)
        else:
            raise Exception("Only .csv and .xlsx files are supported.")

    def _parse_xlsx(self, file):
        # Read all sheets with pandas (no header assumption)
        xl = pd.ExcelFile(file)

        # 1. Try Zerodha format: prefer "Equity" sheet, then "Combined"
        for preferred in ("Equity", "Combined"):
            if preferred in xl.sheet_names:
                df = xl.parse(preferred, header=None)
                if _is_zerodha(df):
                    rows = _parse_zerodha_sheet(df)
                    if rows:
                        return rows

        # 2. Try any sheet in Zerodha format
        for sheet in xl.sheet_names:
            df = xl.parse(sheet, header=None)
            if _is_zerodha(df):
                rows = _parse_zerodha_sheet(df)
                if rows:
                    return rows

        # 3. Fallback: treat first sheet as simple ticker/qty/price format
        file.seek(0)
        return _parse_simple_xlsx(file, self.skipped)

    # ── Build full analysis from normalised rows ──────────────────────────────
    def _build_analysis(self, raw_rows: list):
        stocks       = []
        total_cost   = 0.0
        total_value  = 0.0
        quotes       = self._quotes([r["ticker"] for r in raw_rows])

        for r in raw_rows:
            ticker    = r["ticker"]
            qty       = r["quantity"]
            buy_price = r["buy_price"]

            # Current price: live quote -> price in the uploaded file -> buy price (flagged)
            quote = quotes.get(ticker)
            if quote:
                current_price, price_source = quote["price"], f"live ({quote['source']})"
            elif r.get("current_price"):
                current_price, price_source = r["current_price"], "from your file"
            else:
                current_price, price_source = buy_price, "unavailable (buy price used)"

            cost_basis  = qty * buy_price
            current_val = qty * current_price

            pnl     = current_val - cost_basis
            pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0

            total_cost  += cost_basis
            total_value += current_val

            sector      = (r.get("sector") or SECTORS.get(ticker)
                           or (quote or {}).get("sector") or "Other")
            volatility  = (quote or {}).get("volatility")
            is_high_vol = volatility is not None and volatility > HIGH_VOL_DAILY_PCT
            pe          = (quote or {}).get("pe")

            # Per-stock call. Uses the same trend/RSI reading as the full analysis so the
            # two screens never disagree, and every call carries its own reason.
            trend = (quote or {}).get("trend")
            rsi   = (quote or {}).get("rsi")
            if not price_source.startswith("live"):
                rec, why = "REVIEW", "No live price found; check the NSE symbol before acting."
                if ticker in RENAMED:
                    why = f"No live price for {ticker}; it now trades as {RENAMED[ticker]}."
            elif pnl_pct > 30 and pe and pe > 25:
                rec, why = "SELL", f"Up {pnl_pct:.1f}% at a rich P/E of {pe:.0f}; consider booking part."
            elif pnl_pct < -15:
                rec, why = "REVIEW", f"Down {abs(pnl_pct):.1f}%; check the reason you bought still holds."
            elif trend == "Downtrend":
                rec, why = "HOLD", "Price is still falling; wait for the trend to turn before adding."
            elif rsi is not None and rsi > 75:
                rec, why = "HOLD", f"Overbought (RSI {rsi:.0f}) after a sharp rise; wait for a pullback."
            elif is_high_vol:
                rec, why = "HOLD", f"Volatile ({volatility:.1f}% a day); keep the position size as is."
            elif pnl_pct < 0:
                rec, why = "BUY", "Below your cost and the trend is not falling; adding is reasonable."
            else:
                rec, why = "HOLD", "In profit with a steady trend; keep holding."

            stocks.append({
                "ticker":        ticker,
                "quantity":      qty,
                "buyPrice":      round(buy_price, 2),
                "currentPrice":  round(current_price, 2),
                "costBasis":     round(cost_basis, 2),
                "trend":         trend,
                "rsi":           rsi,
                "history":       (quote or {}).get("history") or [],
                "reason":        why,
                "currentValue":  round(current_val, 2),
                "pnl":           round(pnl, 2),
                "pnlPct":        round(pnl_pct, 2),
                "sector":        sector,
                "recommendation": rec,
                "isHighVol":     is_high_vol,
                "volatility":    volatility,
                "pe":            round(pe, 1) if pe else None,
                "priceSource":   price_source,
            })

        if not stocks:
            raise Exception("No valid stock rows found after parsing.")

        total_pnl     = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

        for s in stocks:
            s["weight"] = round(s["currentValue"] / total_value * 100, 1) if total_value else 0

        # Sector allocation
        sector_vals = {}
        for s in stocks:
            sector_vals[s["sector"]] = sector_vals.get(s["sector"], 0) + s["currentValue"]

        sector_allocation = {
            sec: round(val / total_value * 100, 1)
            for sec, val in sector_vals.items()
        } if total_value else {}

        risk_score  = self._portfolio_risk(stocks, total_value, sector_allocation)
        div_score   = self._diversification_score(stocks, sector_allocation)
        advice      = self._generate_advice(stocks, total_value, sector_allocation, risk_score, div_score)
        recs        = self._per_stock_recommendations(stocks, total_value)
        style       = self._detect_style(stocks, sector_allocation)

        return {
            "stocks":               stocks,
            "totalValue":           round(total_value, 2),
            "totalCost":            round(total_cost, 2),
            "totalPnL":             round(total_pnl, 2),
            "totalPnLPct":          round(total_pnl_pct, 2),
            "riskScore":            risk_score,
            "diversificationScore": div_score,
            "sectorAllocation":     sector_allocation,
            "investmentStyle":      style,
            "advice":               advice,
            "recommendations":      recs,
            "livePriced":           sum(1 for s in stocks if s["priceSource"].startswith("live")),
        }

    # ── Risk score (0–100) ────────────────────────────────────────────────────
    def _portfolio_risk(self, stocks, total_value, sector_alloc):
        score = 20
        for s in stocks:
            w = s["currentValue"] / total_value * 100 if total_value else 0
            if w > 40: score += 25
            elif w > 25: score += 12

        hv_weight = sum(s["currentValue"] for s in stocks if s["isHighVol"])
        hv_pct    = hv_weight / total_value * 100 if total_value else 0
        if hv_pct > 40: score += 20
        elif hv_pct > 20: score += 10

        max_sector = max(sector_alloc.values()) if sector_alloc else 0
        if max_sector > 60: score += 20
        elif max_sector > 40: score += 10

        if len(stocks) <= 2:   score += 15
        elif len(stocks) <= 4: score += 5

        return min(100, score)

    # ── Diversification score (0–100) ────────────────────────────────────────
    def _diversification_score(self, stocks, sector_alloc):
        score = 0
        n = len(stocks)
        if n >= 10:   score += 40
        elif n >= 6:  score += 25
        elif n >= 3:  score += 12

        ns = len(sector_alloc)
        if ns >= 5:   score += 35
        elif ns >= 3: score += 20
        else:          score += 5

        if sector_alloc:
            ms = max(sector_alloc.values())
            if ms < 30:   score += 25
            elif ms < 50: score += 10

        return min(100, score)

    # ── Investment style ──────────────────────────────────────────────────────
    def _detect_style(self, stocks, sector_alloc):
        etf_wt  = sector_alloc.get("ETF", 0)
        it_fin  = sector_alloc.get("IT", 0) + sector_alloc.get("Finance", 0)
        bank_en = sector_alloc.get("Banking", 0) + sector_alloc.get("Oil & Gas", 0) + sector_alloc.get("Utilities", 0)
        if etf_wt > 40:   return "Passive / Index Investor"
        if it_fin > 50:   return "Growth Investor"
        if bank_en > 50:  return "Value / Dividend Investor"
        if len(stocks) >= 8: return "Diversified Long-Term Investor"
        return "Concentrated Stock Picker"

    # ── Advice generation ─────────────────────────────────────────────────────
    def _generate_advice(self, stocks, total_value, sector_alloc, risk_score, div_score):
        advice = []

        for s in stocks:
            w = s["currentValue"] / total_value * 100 if total_value else 0
            if w > 35:
                advice.append(f"{s['ticker']} is {w:.1f}% of your portfolio – consider trimming.")

        for sec, pct in sector_alloc.items():
            if pct > 50:
                advice.append(f"{pct:.0f}% exposure to {sec} — consider diversifying.")

        if len(stocks) <= 3:
            advice.append("Very few stocks. Adding 4–8 more across sectors improves resilience.")

        hv = [s["ticker"] for s in stocks if s["isHighVol"]]
        if hv:
            advice.append(f"High daily volatility (>{HIGH_VOL_DAILY_PCT}%): {', '.join(hv)}. Consider setting stop-losses.")

        if div_score < 40:
            advice.append("Low diversification. Consider adding NIFTYBEES or GOLDBEES for broad market exposure.")

        for s in stocks:
            pe = s.get("pe")
            if pe and pe > 28 and s["pnlPct"] > 20:
                advice.append(f"{s['ticker']} has premium P/E ({pe}x) and is up {s['pnlPct']:.1f}% — consider booking partial profits.")

        for s in stocks:
            if s["pnlPct"] < -10:
                advice.append(f"{s['ticker']} is down {abs(s['pnlPct']):.1f}% — review if fundamentals have changed.")

        if risk_score > 60:
            advice.append("High overall portfolio risk. Consider rebalancing — reduce concentrated positions.")
        elif risk_score > 40:
            advice.append("Moderate portfolio risk. A quarterly rebalancing review is recommended.")

        if not advice:
            advice.append("Portfolio looks reasonably diversified. Keep monitoring quarterly.")

        return advice

    # ── Per-stock recommendations ─────────────────────────────────────────────
    def _per_stock_recommendations(self, stocks, total_value):
        recs = []
        for s in stocks:
            w   = s["currentValue"] / total_value * 100 if total_value else 0
            msg = ""
            if s["pnlPct"] > 25 and w > 25:
                msg = f"Consider trimming — up {s['pnlPct']:.1f}% and heavily weighted at {w:.1f}%."
            else:
                msg = s.get("reason") or "Maintain current position."
            recs.append({"ticker": s["ticker"], "action": s["recommendation"], "note": msg})
        return recs