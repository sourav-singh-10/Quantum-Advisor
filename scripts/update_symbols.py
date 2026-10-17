"""Replace data/nse_companies.csv with NSE's full list of listed equities (about 2,000 companies).

Run on a machine that can reach nseindia.com:
    python scripts/update_symbols.py
"""
import csv
import io
import sys
from pathlib import Path

import requests

URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
OUT = Path(__file__).resolve().parents[1] / "data" / "nse_companies.csv"


def main() -> int:
    try:
        r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
    except requests.RequestException as exc:
        print(f"Could not download the NSE list: {exc}")
        return 1
    rows = list(csv.DictReader(io.StringIO(r.text)))
    rows = [{"SYMBOL": x["SYMBOL"].strip(), "NAME OF COMPANY": x["NAME OF COMPANY"].strip()}
            for x in rows if x.get("SYMBOL") and x.get("NAME OF COMPANY")]
    if len(rows) < 500:
        print(f"Only {len(rows)} rows came back; keeping the existing list.")
        return 1
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["SYMBOL", "NAME OF COMPANY"])
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} companies to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
