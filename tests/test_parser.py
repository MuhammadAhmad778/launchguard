import pytest

from compose_parser import ComposeError, normalize_port, parse_compose


@pytest.mark.parametrize("entry,host,published,target,protocol,binding", [
    ("8080:80", None, 8080, 80, "tcp", "wildcard"),
    ("127.0.0.1:8080:80", "127.0.0.1", 8080, 80, "tcp", "loopback"),
    ("127.2.3.4:8080:80", "127.2.3.4", 8080, 80, "tcp", "loopback"),
    ("0.0.0.0:8080:80", "0.0.0.0", 8080, 80, "tcp", "wildcard"),
    ("[::1]:8080:80", "::1", 8080, 80, "tcp", "loopback"),
    ("[::]:8080:80", "::", 8080, 80, "tcp", "wildcard"),
    ("10.0.0.2:8080:80", "10.0.0.2", 8080, 80, "tcp", "non-loopback"),
    ("5353:53/udp", None, 5353, 53, "udp", "wildcard"),
    ("80", None, None, 80, "tcp", "wildcard"),
    (80, None, None, 80, "tcp", "wildcard"),
    ({"target": 53, "published": "5353", "host_ip": "::1", "protocol": "udp"}, "::1", 5353, 53, "udp", "loopback"),
    ({"target": 80}, None, None, 80, "tcp", "wildcard"),
])
def test_supported_ports(entry, host, published, target, protocol, binding):
    port, error = normalize_port(entry, "web", 0, 7)
    assert error is None
    assert (port.host_ip, port.published_port, port.target_port, port.protocol, port.binding) == (host, published, target, protocol, binding)
    assert port.source_line == 7


@pytest.mark.parametrize("entry", ["8000-8002:80", "${PORT}:80", "65536:80", "0:80", "80:0", "80:80/sctp", True,
                                  "localhost:80:80", "::1:80:80", "[garbage]:80:80", "999.1.1.1:80:80",
                                  {"target": 80, "mode": "ingress"}, {"target": 80, "host_ip": None},
                                  {"target": 80, "published": ""}, {"target": "${SECRET}"}])
def test_unresolved_ports(entry):
    port, reason = normalize_port(entry, "app", 0)
    assert port is None and reason


@pytest.mark.parametrize("text", ["", "[]", "services: {}", "services: []", "services: {a: null}",
                                 "services: {a: {}}\n---\nservices: {b: {}}", "services: [", 
                                 "services:\n  a: {}\n  a: {}", "services: {a: {ports: [], ports: []}}",
                                 "services: {a: &a {environment: *a}}", "services: {a: !!python/object/apply:os.system [bad]}",
                                 "services: {a: {environment: {<<: {A: b}}}}"])
def test_invalid_yaml(text):
    with pytest.raises(ComposeError):
        parse_compose(text)


def test_input_bounds():
    with pytest.raises(ComposeError, match="100 KB"):
        parse_compose("#" * 100_001)
    with pytest.raises(ComposeError, match="depth"):
        parse_compose("a: " + "[" * 32 + "0" + "]" * 32)
    with pytest.raises(ComposeError, match="50"):
        parse_compose("services:\n" + "\n".join(f"  s{i}: {{}}" for i in range(51)))


def test_lines_and_expose():
    doc = parse_compose('services:\n  web:\n    expose: [80]\n    ports:\n      - "8080:80"\n')
    assert doc.services["web"].ports[0].source_line == 5
    assert not parse_compose("services: {web: {expose: [80]}}").services["web"].ports


@pytest.mark.parametrize("field,value", [("network_mode", "host"), ("network_mode", "service:other"),
                                        ("extends", {"service": "base"}), ("deploy", {"replicas": 2})])
def test_unsupported_is_service_scoped(make_document, field, value):
    assert make_document(["8080:80"], **{field: value}).services["app"].unresolved
    doc = parse_compose('services: {bad: {network_mode: host}, good: {ports: ["80:80"]}}')
    assert not doc.services["good"].unresolved


def test_no_interpolation_from_process_environment(monkeypatch, make_document):
    monkeypatch.setenv("PORT", "8080")
    assert make_document(["${PORT}:80"]).services["app"].unresolved


def test_default_and_explicit_networks():
    doc = parse_compose("services: {a: {}, b: {}}")
    assert doc.services["a"].networks == doc.services["b"].networks == {"default"}
    doc = parse_compose("services: {a: {networks: [app]}}\nnetworks: {app: {driver: bridge}}")
    assert doc.services["a"].networks == {"app"}


@pytest.mark.parametrize("text", [
    "services: {a: {networks: [absent]}}",
    "services: {a: {}}\nnetworks: {default: {driver_opts: {x: y}}}",
    "services: {a: {networks: [n]}}\nnetworks: {n: {external: true}}",
    "services: {a: {}}\ninclude: other.yml",
])
def test_network_unknowns(text):
    doc = parse_compose(text)
    assert doc.services["a"].unresolved
    assert not doc.services["a"].networks


def test_yaml_scalar_preservation():
    doc = parse_compose('services: {a: {environment: {YES_VALUE: yes, CODE: 0123, DATE: 2026-01-01, TIME: "12:30"}}}')
    assert doc.data["services"]["a"]["environment"] == {"YES_VALUE": "yes", "CODE": "0123", "DATE": "2026-01-01", "TIME": "12:30"}


@pytest.mark.parametrize("definition", ["false", "42", "[]", "text"])
def test_invalid_network_definition_not_treated_as_default(definition):
    doc = parse_compose("services: {a: {}}\nnetworks: {default: " + definition + "}")
    assert doc.services["a"].unresolved
