"""Capture a GENUINE run from a deployed instance as submission evidence.

Usage (after deploying, with a real account on the live site):
    python scripts/capture_run.py https://<your-app>.onrender.com you@example.com yourpassword \
        --ticker RELIANCE --age 62 --risk Conservative --horizon Short-term --name conflict

For a portfolio review instead of a stock analysis:
    python scripts/capture_run.py https://<your-app>.onrender.com you@example.com yourpassword \
        --portfolio frontend/samples/sample_portfolio.csv --name portfolio

Writes, unedited:
    docs/samples/<name>_request.json    (or <name>_request.csv for a portfolio)
    docs/samples/<name>_response.json   (without the embedded trace)
    docs/traces/<name>.jsonl            (one agent message per line, exactly as logged)
Never edit these files by hand: CA3 treats an edited trace as an integrity violation.
"""
import argparse
import json
import shutil
import sys
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
    ap.add_argument("--document", default=None, help="path to the company's annual report PDF")
    ap.add_argument("--portfolio", default=None, help="CSV or XLSX of holdings: capture a portfolio review")
    ap.add_argument("--signup", action="store_true",
                    help="create the account first if it does not exist yet")
    a = ap.parse_args()

    s = requests.Session()
    r = s.post(f"{a.base_url}/login", json={"email": a.email, "password": a.password}, timeout=60)
    if r.status_code == 401 and a.signup:
        r = s.post(f"{a.base_url}/signup", json={"email": a.email, "password": a.password}, timeout=60)
    if r.status_code >= 400:
        sys.exit(f"Could not sign in as {a.email} (HTTP {r.status_code}: {r.text[:200]}). "
                 "Check the password, or add --signup to create this account first.")
    (ROOT / "docs/samples").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/traces").mkdir(parents=True, exist_ok=True)
    if a.portfolio:
        src = Path(a.portfolio)
        with src.open("rb") as fh:
            r = s.post(f"{a.base_url}/upload_portfolio", files={"file": (src.name, fh)}, timeout=600)
        shutil.copyfile(src, ROOT / f"docs/samples/{a.name}_request{src.suffix.lower()}")
        save(a.name, r)
        return
    body = {"ticker": a.ticker, "age": a.age, "experience": a.experience,
            "riskAppetite": a.risk, "timeHorizon": a.horizon, "portfolioValue": a.value}
    if a.goal:
        body["goal"] = a.goal
    if a.document:
        with open(a.document, "rb") as fh:
            r = s.post(f"{a.base_url}/api/analyze", data={k: str(v) for k, v in body.items()},
                       files={"document": (Path(a.document).name, fh, "application/pdf")},
                       timeout=600)
        body["document"] = Path(a.document).name
    else:
        r = s.post(f"{a.base_url}/api/analyze", json=body, timeout=300)
    (ROOT / f"docs/samples/{a.name}_request.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
    save(a.name, r)


def save(name: str, r) -> None:
    """Write the response (without its trace) and the trace, exactly as the server sent them."""
    out = r.json()
    trace = out.pop("trace", [])
    (ROOT / f"docs/samples/{name}_response.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    with (ROOT / f"docs/traces/{name}.jsonl").open("w", encoding="utf-8") as fh:
        for e in trace:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    meta = out.get("meta", {})
    calls, failures = meta.get("llmCalls", 0), meta.get("llmFailures", 0)
    print(f"HTTP {r.status_code} run {meta.get('runId')} status {meta.get('status')} "
          f"rec {out.get('recommendation')} rounds {meta.get('debateRounds')} "
          f"replans {meta.get('replans')} messages {len(trace)}")
    print(f"{calls - failures} of {calls} decisions by the model"
          + ("" if calls and not failures else "  <- rule fallback used: capture again later before using this as a sample"))


if __name__ == "__main__":
    main()
