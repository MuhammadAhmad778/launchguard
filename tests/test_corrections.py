from copy import deepcopy

import pytest

from corrections import CorrectionError, propose
from models import Intent


def test_demo_correction_preserves_unrelated_values(demo):
    doc, intents = demo
    original = deepcopy(doc.data)
    candidate = propose(doc, intents, ["database", "admin"])
    assert candidate.removed_findings == 2
    assert not candidate.analysis.findings
    assert doc.data == original  # No mutation of the original input.
    assert candidate.document.data["services"]["web"] == original["services"]["web"]
    assert candidate.document.data["services"]["database"]["environment"] == original["services"]["database"]["environment"]
    assert candidate.document.data["services"]["database"]["volumes"] == original["services"]["database"]["volumes"]
    assert candidate.document.data["networks"] == original["networks"]
    assert "ports" not in candidate.document.data["services"]["database"]


@pytest.mark.parametrize("port", ["5353:53/udp", "[::]:5353:53/udp", "80",
                                  {"target": 80, "published": "8080", "name": "keep-me", "app_protocol": "http"}])
def test_loopback_preserves_target_published_protocol(make_document, port):
    doc = make_document([port])
    before = doc.services["app"].ports[0]
    candidate = propose(doc, {"app": Intent.LOCAL}, ["app"])
    after = candidate.document.services["app"].ports[0]
    assert (before.target_port, before.published_port, before.protocol) == (after.target_port, after.published_port, after.protocol)
    assert after.binding == "loopback"
    if before.host_ip == "::":
        assert after.host_ip == "::1"
    if isinstance(port, dict):
        assert candidate.document.data["services"]["app"]["ports"][0]["name"] == "keep-me"


def test_idempotence(demo):
    doc, intents = demo
    candidate = propose(doc, intents, ["database", "admin"])
    again = propose(candidate.document, intents, ["database", "admin"])
    assert again.text == candidate.text
    assert again.removed_findings == 0


def test_unresolved_rejected(make_document):
    doc = make_document(["80:80", "${P}:81"])
    with pytest.raises(CorrectionError, match="unresolved"):
        propose(doc, {"app": Intent.APPLICATION}, ["app"])


def test_external_correction_rejected(make_document):
    with pytest.raises(CorrectionError):
        propose(make_document(), {"app": Intent.EXTERNAL}, ["app"])


def test_other_loopback_entries_remain_exactly_unchanged(make_document):
    doc = make_document(["127.0.0.1:8080:80", "5353:53/udp"])
    candidate = propose(doc, {"app": Intent.LOCAL}, ["app"])
    assert candidate.document.data["services"]["app"]["ports"][0] == "127.0.0.1:8080:80"


def test_long_form_only_host_ip_changes(make_document):
    original = {"target": 80, "published": 8080, "protocol": "tcp", "name": "http"}
    doc = make_document([original], cpus=0.5)
    candidate = propose(doc, {"app": Intent.LOCAL}, ["app"])
    assert candidate.document.data["services"]["app"]["ports"][0] == {**original, "host_ip": "127.0.0.1"}
    assert candidate.document.data["services"]["app"]["cpus"] == 0.5
