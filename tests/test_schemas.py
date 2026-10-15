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


def validator():
    trace = load("trace_event.schema.json")
    registry = Registry().with_resource("trace_event.schema.json", Resource.from_contents(trace))
    return jsonschema.Draft202012Validator(load("analyze_response.schema.json"), registry=registry)


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
