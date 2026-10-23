from pathlib import Path

from streamlit.testing.v1 import AppTest
import ai_client
from ai_client import AISettings


APP = Path(__file__).parents[1] / "app.py"


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_full_demo_and_stale_state(monkeypatch):
    monkeypatch.setattr(ai_client, "read_settings", lambda path=None: AISettings("", ""))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LAUNCHGUARD_MODEL", raising=False)
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    button(app, "Load demo configuration").click().run()
    button(app, "Parse configuration").click().run()
    assert len(app.radio) == 3
    button(app, "Use demo intentions").click().run()
    button(app, "Analyze intent").click().run()
    assert [metric.value for metric in app.metric] == ["2", "0", "0", "1"]
    button(app, "Preview correction and reanalyze").click().run()
    assert not app.exception
    assert app.session_state["candidate"].removed_findings == 2
    app.toggle[0].set_value(False).run()
    assert app.session_state["candidate"].removed_findings == 2
    assert app.session_state["step"] == 3
    app.toggle[0].set_value(True).run()
    assert app.session_state["candidate"].removed_findings == 2
    button(app, "Explain findings with AI").click().run()
    assert not app.exception
    assert any("optional" in message.value for message in app.info)
    button(app, "Edit access intentions").click().run()
    assert [box.value for box in app.radio] == ["External access intended", "Application-only", "Host-local"]
    app.radio[0].set_value("Host-local").run()
    assert "analysis" not in app.session_state
    assert "candidate" not in app.session_state
    button(app, "Analyze intent").click().run()
    button(app, "1 · Configuration").click().run()
    assert "postgres:17" in app.text_area[0].value
    app.text_area[0].set_value("services: {new: {}}").run()
    assert "document" not in app.session_state
    assert not app.metric
    assert not app.exception


def test_ai_explanation_uses_current_settings_and_clears_stale_result(monkeypatch):
    current = [AISettings("fake-key", "gemini-test-one")]
    monkeypatch.setattr(ai_client, "read_settings", lambda path=None: current[0])
    def fake_explain(payload, **kwargs):
        assert kwargs["settings"] == current[0]
        return {"summary": "Mocked explanation for " + current[0].model}
    monkeypatch.setattr(ai_client, "explain", fake_explain)
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    button(app, "Load demo configuration").click().run()
    button(app, "Parse configuration").click().run()
    button(app, "Use demo intentions").click().run()
    button(app, "Analyze intent").click().run()
    button(app, "Explain findings with AI").click().run()
    assert app.session_state["ai_result"]["summary"].endswith("gemini-test-one")
    current[0] = AISettings("new-fake-key", "gemini-test-two")
    app.run()
    assert "ai_result" not in app.session_state
    assert "analysis" in app.session_state
    button(app, "Explain findings with AI").click().run()
    assert app.session_state["ai_result"]["summary"].endswith("gemini-test-two")
    assert not app.exception

def test_reset_requires_confirmation_and_preserves_theme(monkeypatch):
    monkeypatch.setattr(ai_client, "read_settings", lambda path=None: AISettings("", ""))
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    button(app, "Load demo configuration").click().run()
    button(app, "Parse configuration").click().run()
    button(app, "Use demo intentions").click().run()
    button(app, "Analyze intent").click().run()
    button(app, "Reset review").click().run()
    assert "analysis" in app.session_state
    button(app, "Keep current review").click().run()
    assert "analysis" in app.session_state
    button(app, "Reset review").click().run()
    button(app, "Confirm reset").click().run()
    assert app.session_state["step"] == 1
    assert "document" not in app.session_state
    assert "analysis" not in app.session_state
    assert app.text_area[0].value == ""
    assert app.toggle[0].value is True
    assert not app.exception


def test_invalid_yaml_and_replacement_preserve_input(monkeypatch):
    monkeypatch.setattr(ai_client, "read_settings", lambda path=None: AISettings("", ""))
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    original = "services: [broken"
    app.text_area[0].set_value(original).run()
    button(app, "Parse configuration").click().run()
    assert app.error and app.session_state["step"] == 1
    assert app.text_area[0].value == original
    button(app, "Load demo configuration").click().run()
    assert app.text_area[0].value == original
    button(app, "Keep current review").click().run()
    assert app.text_area[0].value == original
    button(app, "Load demo configuration").click().run()
    button(app, "Confirm replacement").click().run()
    button(app, "Parse configuration").click().run()
    assert len(app.radio) == 3
    assert not app.exception


def test_candidate_reanalysis_and_unchanged_configuration_preserve_review(monkeypatch):
    monkeypatch.setattr(ai_client, "read_settings", lambda path=None: AISettings("", ""))
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    button(app, "Load demo configuration").click().run()
    button(app, "Parse configuration").click().run()
    button(app, "Use demo intentions").click().run()
    button(app, "Analyze intent").click().run()
    button(app, "Preview correction and reanalyze").click().run()
    expected = app.session_state["candidate"].text
    button(app, "Reanalyze candidate").click().run()
    assert app.session_state["candidate"].text == expected
    assert not app.session_state["candidate"].analysis.findings
    button(app, "1 · Configuration").click().run()
    button(app, "Parse configuration").click().run()
    assert app.session_state["candidate"].text == expected
    assert [r.value for r in app.radio] == ["External access intended", "Application-only", "Host-local"]
    assert not app.exception

def test_provider_failure_preserves_facts_and_candidate(monkeypatch):
    monkeypatch.setattr(ai_client, "read_settings", lambda path=None: AISettings("fake", "gemma-4-test"))
    def unavailable(*args, **kwargs):
        raise ai_client.AIError("Google returned HTTP 503: the model service failed or timed out.")
    monkeypatch.setattr(ai_client, "explain", unavailable)
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    button(app, "Load demo configuration").click().run()
    button(app, "Parse configuration").click().run()
    button(app, "Use demo intentions").click().run()
    button(app, "Analyze intent").click().run()
    button(app, "Preview correction and reanalyze").click().run()
    button(app, "Explain findings with AI").click().run()
    assert any("HTTP 503" in w.value for w in app.warning)
    assert len(app.session_state["analysis"].findings) == 2
    assert app.session_state["candidate"].removed_findings == 2
    assert not app.exception
