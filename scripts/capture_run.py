"""Capture a GENUINE run from a deployed instance as submission evidence.

Usage (after deploying, with a real account on the live site):
    python scripts/capture_run.py https://<your-app>.onrender.com you@example.com yourpassword \
        --ticker RELIANCE --age 62 --risk Conservative --horizon Short-term --name conflict

Writes, unedited:
    docs/samples/<name>_request.json
    docs/samples/<name>_response.json   (without the embedded trace)
    docs/traces/<name>.jsonl            (one agent message per line, exactly as logged)
Never edit these files by hand: CA3 treats an edited trace as an integrity violation.
"""
import argparse
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("email")
    ap.add_argument("password")
    ap.add_argument("--name", required=True, help="label, e.g. normal / conflict / failure")
    ap.add_argument("--ticker", default="RELIANCE")
    ap.add_argument("--age", type=int, default=30)
    ap.add_argument("--experience", default="Intermediate")
    ap.add_argument("--risk", default="Moderate")
    ap.add_argument("--horizon", default="Medium-term")
    ap.add_argument("--value", type=float, default=100000)
    ap.add_argument("--goal", default=None)
    a = ap.parse_args()

    s = requests.Session()
    r = s.post(f"{a.base_url}/login", json={"email": a.email, "password": a.password}, timeout=30)
    r.raise_for_status()
    body = {"ticker": a.ticker, "age": a.age, "experience": a.experience,
            "riskAppetite": a.risk, "timeHorizon": a.horizon, "portfolioValue": a.value}
    if a.goal:
        body["goal"] = a.goal
    r = s.post(f"{a.base_url}/api/analyze", json=body, timeout=300)
    out = r.json()
    trace = out.pop("trace", [])

    (ROOT / "docs/samples").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/traces").mkdir(parents=True, exist_ok=True)
    (ROOT / f"docs/samples/{a.name}_request.json").write_text(json.dumps(body, indent=2))
    (ROOT / f"docs/samples/{a.name}_response.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))
    with (ROOT / f"docs/traces/{a.name}.jsonl").open("w", encoding="utf-8") as fh:
        for e in trace:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    meta = out.get("meta", {})
    print(f"HTTP {r.status_code} run {meta.get('runId')} status {meta.get('status')} "
          f"rec {out.get('recommendation')} rounds {meta.get('debateRounds')} "
          f"replans {meta.get('replans')} messages {len(trace)}")


if __name__ == "__main__":
    main()
