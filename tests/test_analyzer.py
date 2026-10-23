import pytest

from analyzer import analyze, shared_networks
from models import Intent


@pytest.mark.parametrize("intent,ports,expected", [
    (Intent.APPLICATION, ["80:80"], ["LG001"]),
    (Intent.APPLICATION, ["80"], ["LG001"]),
    (Intent.APPLICATION, [], []),
    (Intent.LOCAL, ["80:80"], ["LG002"]),
    (Intent.LOCAL, ["127.0.0.1:80:80"], []),
    (Intent.LOCAL, ["[::1]:80:80"], []),
    (Intent.LOCAL, ["10.1.1.1:80:80"], ["LG003"]),
    (Intent.EXTERNAL, ["80:80"], []),
    (Intent.EXTERNAL, [], ["LG004"]),
    (Intent.EXTERNAL, ["127.0.0.1:80:80"], ["LG004"]),
    (Intent.UNSPECIFIED, [], ["LG006"]),
])
def test_rules(make_document, intent, ports, expected):
    result = analyze(make_document(ports), {"app": intent})
    assert [f.rule_id for f in result.findings] == expected
    assert bool(result.consistent_services) == (not expected)


def test_unresolved_is_not_consistent(make_document):
    doc = make_document(["${PORT}:80"])
    for intent in (Intent.APPLICATION, Intent.LOCAL, Intent.EXTERNAL):
        result = analyze(doc, {"app": intent})
        assert not result.consistent_services
        assert [f.rule_id for f in result.findings] == ["LG005"]
        assert not any(f.correction_available for f in result.findings)


def test_demo(demo):
    doc, intents = demo
    result = analyze(doc, intents)
    assert [(f.service_name, f.rule_id) for f in result.findings] == [("database", "LG001"), ("admin", "LG002")]
    assert result.consistent_services == ["web"]
    assert shared_networks(doc, "database") == {"service-1": 1, "service-3": 1}


def test_external_missing_is_review(make_document):
    finding = analyze(make_document(), {"app": Intent.EXTERNAL}).findings[0]
    assert finding.category == "Review" and not finding.correction_available
