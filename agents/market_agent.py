import requests
import pandas as pd
import numpy as np

from config import MARKETSTACK_API_KEY, ALPHAVANTAGE_API_KEY


class MarketAgent:

    # ==============================
    # MARKETSTACK HISTORY
    # ==============================
    def get_marketstack_history(self, symbol):

        url = "http://api.marketstack.com/v1/eod"

        params = {
            "access_key": MARKETSTACK_API_KEY,
            "symbols": symbol + ".XNSE",
            "limit": 100,
        }

        try:

            r = requests.get(url, params=params)

            data = r.json()

            if "data" not in data or not data["data"]:
                return None

            prices = [d["close"] for d in data["data"]]

            prices.reverse()

            return prices

        except:

            return None

    # ==============================
    # ALPHAVANTAGE HISTORY
    # ==============================
    def get_alpha_history(self, symbol):

        url = "https://www.alphavantage.co/query"

        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol + ".BSE",
            "apikey": ALPHAVANTAGE_API_KEY,
        }

        try:

            r = requests.get(url, params=params)

            data = r.json()

            ts = data.get("Time Series (Daily)", None)

            if not ts:
                return None

            prices = []

            for d in ts.values():

                prices.append(float(d["4. close"]))

            prices.reverse()

            return prices

        except:

            return None

    # ==============================
    # INDICATORS
    # ==============================
    def compute_indicators(self, prices):

        series = pd.Series(prices)

        price = series.iloc[-1]

        # RSI
        delta = series.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()

        rs = avg_gain / avg_loss

        rsi = 100 - (100 / (1 + rs))

        rsi_val = float(rsi.iloc[-1])

        # volatility
        returns = series.pct_change()

        vol = float(returns.std() * 100)

        # trend

        ma20 = series.rolling(20).mean().iloc[-1]
        ma50 = series.rolling(50).mean().iloc[-1]

        if ma20 > ma50:
            trend = "Uptrend"
        elif ma20 < ma50:
            trend = "Downtrend"
        else:
            trend = "Sideways"

        return price, rsi_val, vol, trend

    # ==============================
    # MAIN ANALYZE
    # ==============================
    def analyze(self, ticker):

        symbol = ticker.upper()

        prices = None
        source = None

        # 1️⃣ MarketStack

        prices = self.get_marketstack_history(symbol)

        if prices:
            source = "MarketStack"

        # 2️⃣ AlphaVantage fallback

        if not prices:

            prices = self.get_alpha_history(symbol)

            if prices:
                source = "AlphaVantage"

        if not prices:
            raise Exception("No data from any API")

        price, rsi, vol, trend = self.compute_indicators(prices)

        return {

            "ticker": symbol,
            "currentPrice": round(price, 2),
            "priceDisplay": f"₹{price:.2f}",
            "trend": trend,
            "rsi": round(rsi, 2),
            "volatility": round(vol, 2),
            "priceSource": source,
        }