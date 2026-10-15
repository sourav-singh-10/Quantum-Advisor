import requests
from config import MARKETSTACK_API_KEY


def fetch_price(ticker):

    symbol = ticker.upper() + ".XNSE"

    url = "http://api.marketstack.com/v1/eod/latest"

    params = {
        "access_key": MARKETSTACK_API_KEY,
        "symbols": symbol,
    }

    r = requests.get(url, params=params)

    data = r.json()

    if data["data"]:

        price = data["data"][0]["close"]

        return price, "MarketStack"

    return None