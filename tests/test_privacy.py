import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
import yaml

from ai_client import AIError, AISettings, build_payload, explain, validate_response, read_settings
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
    assert captured["http_options"].timeout == 45_000
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


def test_settings_reload_local_edits_without_sticky_env(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.setenv("LAUNCHGUARD_MODEL", "stale-process-model")
    monkeypatch.setenv("GEMINI_API_KEY", "stale-process-key")
    path.write_text("GEMINI_API_KEY=first-fake-key\nLAUNCHGUARD_MODEL=first-model\n")
    assert read_settings(path).model == "first-model"
    path.write_text("GEMINI_API_KEY=second-fake-key\nLAUNCHGUARD_MODEL=second-model\n")
    settings = read_settings(path)
    assert settings.model == "second-model"
    assert settings.api_key == "second-fake-key"
    assert "second-fake-key" not in repr(settings)
    path.write_text("GEMINI_API_KEY=\nLAUNCHGUARD_MODEL=\n")
    assert not read_settings(path).configured
    assert read_settings().model == "stale-process-model"


@pytest.mark.parametrize("code,expected", [(404, "HTTP 404"), (504, "HTTP 504"), (429, "HTTP 429"), (403, "access"), (400, "HTTP 400")])
def test_provider_status_has_actionable_safe_error(code, expected):
    class ProviderError(Exception):
        pass
    def broken(**kwargs):
        error = ProviderError(SECRET)
        error.code = code
        raise error
    with pytest.raises(AIError) as caught:
        explain({}, client_factory=broken, settings=AISettings(SECRET, "test-model"))
    assert expected in str(caught.value)
    assert SECRET not in str(caught.value)


def test_gemini_requests_json_without_substituting_model():
    captured = {}
    class Client:
        def __init__(self, **kwargs):
            self.models = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=json.dumps(valid_response()))
    explain({}, client_factory=Client, settings=AISettings(SECRET, "gemini-3.1-flash-lite"))
    assert captured["config"].response_mime_type == "application/json"
    assert captured["model"] == "gemini-3.1-flash-lite"


@pytest.mark.parametrize("status,expected_calls", [(503, 2), (504, 2), (404, 1), (429, 1)])
def test_only_temporary_server_failures_are_retried(monkeypatch, status, expected_calls):
    monkeypatch.setattr("ai_client.time.sleep", lambda seconds: None)
    calls = []
    class Client:
        def __init__(self, **kwargs):
            self.models = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def generate_content(self, **kwargs):
            calls.append(kwargs["model"])
            if len(calls) == 1:
                error = RuntimeError(SECRET)
                error.code = status
                raise error
            return SimpleNamespace(text=json.dumps(valid_response()))
    if expected_calls == 2:
        result = explain({}, client_factory=Client, settings=AISettings(SECRET, "test-model"))
        assert result == valid_response()
    else:
        with pytest.raises(AIError):
            explain({}, client_factory=Client, settings=AISettings(SECRET, "test-model"))
    assert calls == ["test-model"] * expected_calls


def test_persistent_provider_failure_stops_after_two_attempts(monkeypatch):
    monkeypatch.setattr("ai_client.time.sleep", lambda seconds: None)
    calls = []
    class Client:
        def __init__(self, **kwargs):
            self.models = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def generate_content(self, **kwargs):
            calls.append(1)
            error = RuntimeError(SECRET)
            error.code = 503
            raise error
    with pytest.raises(AIError, match="HTTP 503"):
        explain({}, client_factory=Client, settings=AISettings(SECRET, "test-model"))
    assert len(calls) == 2
