"""The documented I/O schemas must match what the code really returns."""
import json
from pathlib import Path

import jsonschema
from referencing import Registry, Resource

from core.runner import run_analysis
from core.schemas import AnalyzeRequest
from tests.fakes import FUNDAMENTALS, FakeLLM, patch_data

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def load(name):
    return json.loads((SCHEMAS / name).read_text())


def validator(name="analyze_response.schema.json"):
    trace = load("trace_event.schema.json")
    registry = Registry().with_resource("trace_event.schema.json", Resource.from_contents(trace))
    return jsonschema.Draft202012Validator(load(name), registry=registry)


def test_response_matches_documented_schema(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco profit rises"])
    out = run_analysis(AnalyzeRequest(ticker="TESTCO").model_dump(), llm=FakeLLM(available=False))
    validator().validate(json.loads(json.dumps(out, default=str)))


def test_response_without_optional_analysts_matches_schema(monkeypatch):
    patch_data(monkeypatch, fundamentals=None, headlines=None)
    out = run_analysis(AnalyzeRequest(ticker="TESTCO").model_dump(), llm=FakeLLM(available=False))
    validator().validate(json.loads(json.dumps(out, default=str)))


def test_request_schema_accepts_documented_sample():
    sample = {"ticker": "RELIANCE", "age": 34, "experience": "Intermediate",
              "riskAppetite": "Moderate", "portfolioValue": 200000,
              "timeHorizon": "Long-term", "goal": "Retirement corpus"}
    jsonschema.validate(sample, load("analyze_request.schema.json"))
    AnalyzeRequest.model_validate(sample)


def test_portfolio_response_matches_documented_schema(monkeypatch):
    import io
    import config
    import app as app_module
    monkeypatch.setattr(config, "REQUIRE_LOGIN", False)
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS)
    app_module.init_db()
    res = app_module.app.test_client().post(
        "/upload_portfolio", content_type="multipart/form-data",
        data={"file": (io.BytesIO(b"ticker,quantity,buy_price\nTESTCO,10,90\nOTHER,4,120\n"), "h.csv")})
    assert res.status_code == 200
    validator("portfolio_response.schema.json").validate(res.get_json())


def test_response_with_a_document_conflict_matches_schema(monkeypatch):
    from tools.document_data import load_pdf
    pdf = (Path(__file__).parent / "fixtures" / "demo_annual_report.pdf").read_bytes()
    patch_data(monkeypatch, fundamentals={**FUNDAMENTALS, "profitMargin": 18.0}, headlines=["x"])
    out = run_analysis(AnalyzeRequest(ticker="DEMOIND").model_dump(), llm=FakeLLM(available=False),
                       document=load_pdf(pdf, "demo.pdf"))
    assert out["documentConflicts"] and out["documentCheck"]["trust"] == "both"
    validator().validate(json.loads(json.dumps(out, default=str)))
