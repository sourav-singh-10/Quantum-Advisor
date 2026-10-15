from services.marketstack_service import fetch_price


def get_price(ticker):

    result = fetch_price(ticker)

    if result:
        return result

    return 500, "fallback"