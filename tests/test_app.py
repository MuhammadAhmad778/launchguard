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
    assert len(app.selectbox) == 3
    button(app, "Use demo intentions").click().run()
    button(app, "Analyze intent").click().run()
    assert [metric.value for metric in app.metric] == ["2", "0", "0", "1"]
    button(app, "Preview correction and reanalyze").click().run()
    assert not app.exception
    assert app.session_state["candidate"].removed_findings == 2
    button(app, "Explain findings with AI").click().run()
    assert not app.exception
    assert any("optional" in message.value for message in app.info)
    app.selectbox[0].select("Host-local").run()
    assert "analysis" not in app.session_state
    assert "candidate" not in app.session_state
    button(app, "Analyze intent").click().run()
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
