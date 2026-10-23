import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
import yaml

from ai_client import AIError, build_payload, explain, validate_response
from analyzer import analyze
from compose_parser import ComposeError, parse_compose
from corrections import propose
from models import Intent
from reporting import make_report, safe_diff


SECRET = "FAKE-SECRET-DO-NOT-USE-1234"


def test_secrets_and_untrusted_strings_excluded():
    raw = {"services": {SECRET: {"image": SECRET, "environment": {"PASSWORD": SECRET},
                                "command": SECRET, "labels": {"prompt": SECRET}, "ports": ["8080:80"]}}}
    doc = parse_compose(yaml.safe_dump(raw))
    intents = {SECRET: Intent.APPLICATION}
    analysis = analyze(doc, intents)
    candidate = propose(doc, intents, [SECRET])
    for rendered in (json.dumps(build_payload(doc, analysis, intents, candidate)), make_report(doc, analysis, candidate),
                     safe_diff(doc, candidate.document)):
        assert SECRET not in rendered
    assert SECRET in candidate.text  # Explicitly labeled original-value artifact.
    # Finding evidence and text are sanitized; internal service_name is an identity key only.
    for finding in analysis.findings:
        fields = asdict(finding)
        fields.pop("service_name")
        assert SECRET not in json.dumps(fields)


def test_parser_error_is_sanitized():
    with pytest.raises(ComposeError) as error:
        parse_compose(f"services: [{SECRET}")
    assert SECRET not in str(error.value)


def test_unresolved_reason_is_sanitized():
    doc = parse_compose(yaml.safe_dump({"services": {"app": {"ports": [SECRET]}}}))
    analysis = analyze(doc, {"app": Intent.LOCAL})
    assert SECRET not in make_report(doc, analysis)


def valid_response():
    return {"summary": "Review host publication.", "why_it_matters": ["Access differs from intent."],
            "correction_tradeoffs": ["Some clients may lose access."], "questions_to_confirm": ["Is host access required?"],
            "verification_limits": ["No runtime checks performed."]}


def test_ai_missing_configuration(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LAUNCHGUARD_MODEL", raising=False)
    with pytest.raises(AIError, match="optional"):
        explain({})


def test_sdk_request_and_validation(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    monkeypatch.setenv("LAUNCHGUARD_MODEL", "test-model")
    captured = {}
    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=json.dumps(valid_response()))
    assert explain({"services": []}, client_factory=Client) == valid_response()
    assert captured["model"] == "test-model"
    assert captured["http_options"].timeout == 20_000
    assert SECRET not in captured["contents"]


def test_provider_errors_do_not_leak(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    monkeypatch.setenv("LAUNCHGUARD_MODEL", "test-model")
    def broken(**kwargs):
        raise RuntimeError(SECRET)
    with pytest.raises(AIError) as error:
        explain({}, client_factory=broken)
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("response", ["not json", "[]", "{}", '{"summary": 3}', "x" * 20_001])
def test_bad_ai_response(response):
    with pytest.raises(AIError):
        validate_response(response)
