from pathlib import Path

from streamlit.testing.v1 import AppTest


APP = Path(__file__).parents[1] / "app.py"


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_full_demo_and_stale_state(monkeypatch):
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
