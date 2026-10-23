"""Bounded YAML parsing and conservative Compose port normalization. No execution."""
import ipaddress
import re

import yaml
from yaml.events import AliasEvent, MappingStartEvent, SequenceStartEvent, MappingEndEvent, SequenceEndEvent
from yaml.nodes import MappingNode, SequenceNode

from models import ComposeDocument, Port, Service, Unresolved

MAX_BYTES = 100_000
MAX_SERVICES = 50
MAX_DEPTH = 30
MAX_EVENTS = 12_000


class ComposeError(ValueError):
    """Messages must be static: never echo submitted YAML or parser exceptions."""


class StrictLoader(yaml.SafeLoader):
    pass


# Compose expects YAML 1.2-like scalar behavior. Avoid YAML 1.1 dates, yes/no,
# octal, and sexagesimal integers silently altering unrelated configuration.
StrictLoader.yaml_implicit_resolvers = {
    k: [(tag, pattern) for tag, pattern in values if tag not in {
        "tag:yaml.org,2002:bool", "tag:yaml.org,2002:int", "tag:yaml.org,2002:timestamp",
        "tag:yaml.org,2002:float",
    }]
    for k, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
StrictLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF"))
StrictLoader.add_implicit_resolver("tag:yaml.org,2002:int", re.compile(r"^-?(?:0|[1-9][0-9]*)$"), list("-0123456789"))
StrictLoader.add_implicit_resolver("tag:yaml.org,2002:float", re.compile(
    r"^[-+]?(?:(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?|[0-9]+[eE][-+]?[0-9]+)$"
), list("-+0123456789."))


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str):
            raise ComposeError("YAML mapping keys must be strings. Quote numeric or boolean keys.")
        if key in result:
            raise ComposeError(f"Duplicate YAML mapping key at line {key_node.start_mark.line + 1}.")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


StrictLoader.add_constructor("tag:yaml.org,2002:map", _mapping)


def _locations(node, path=(), result=None):
    if result is None:
        result = {}
    result[path] = node.start_mark.line + 1
    if isinstance(node, MappingNode):
        for key, value in node.value:
            _locations(value, path + (key.value,), result)
    elif isinstance(node, SequenceNode):
        for index, value in enumerate(node.value):
            _locations(value, path + (index,), result)
    return result


def _read_yaml(text):
    if not isinstance(text, str) or not text.strip():
        raise ComposeError("Enter a non-empty Compose YAML document.")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ComposeError("Input exceeds the 100 KB limit.")
    try:
        depth = 0
        for count, event in enumerate(yaml.parse(text, Loader=StrictLoader), 1):
            if count > MAX_EVENTS:
                raise ComposeError("YAML contains too many elements.")
            if isinstance(event, AliasEvent) or getattr(event, "anchor", None):
                raise ComposeError("YAML anchors and aliases are unsupported. Expand them before analysis.")
            if isinstance(event, (MappingStartEvent, SequenceStartEvent)):
                depth += 1
                if depth > MAX_DEPTH:
                    raise ComposeError("YAML nesting exceeds the supported depth.")
            elif isinstance(event, (MappingEndEvent, SequenceEndEvent)):
                depth -= 1
            tag = getattr(event, "tag", None)
            if tag:
                raise ComposeError("Explicit YAML tags and merge directives are unsupported.")
        loader = StrictLoader(text)
        try:
            root = loader.get_single_node()
            if root is None:
                raise ComposeError("Enter a non-empty Compose YAML document.")
            locations = _locations(root)
            data = loader.construct_document(root)
        finally:
            loader.dispose()
    except ComposeError:
        raise
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):
        raise ComposeError("Invalid or unsupported YAML. Check syntax and use one document only.") from None
    if not isinstance(data, dict):
        raise ComposeError("The Compose document must be a mapping.")
    services = data.get("services")
    if not isinstance(services, dict) or not services:
        raise ComposeError("A non-empty services mapping is required.")
    if len(services) > MAX_SERVICES:
        raise ComposeError("The maximum supported service count is 50.")
    if any(not isinstance(v, dict) for v in services.values()):
        raise ComposeError("Each service definition must be a mapping.")
    return data, locations


def _port_number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError
    if not re.fullmatch(r"[0-9]{1,5}", str(value)):
        raise ValueError
    number = int(value)
    if not 1 <= number <= 65535:
        raise ValueError
    return number


def normalize_port(entry, service_name, index, line=None):
    """Invalid syntax returns an unresolved reason, never input values."""
    path = f"services.{service_name}.ports[{index}]"
    try:
        host = None
        published = None
        protocol = "tcp"
        if isinstance(entry, dict):
            allowed = {"target", "published", "host_ip", "protocol", "name", "app_protocol"}
            if set(entry) - allowed:
                return None, "Unsupported long-form port fields or Swarm publication mode."
            if any("$" in str(entry.get(key, "")) for key in ("target", "published", "host_ip", "protocol")):
                return None, "Port interpolation is unresolved; local environment values are not read."
            target = _port_number(entry.get("target"))
            if "published" in entry:
                published = _port_number(entry["published"])
            host = entry.get("host_ip")
            if "host_ip" in entry and (not isinstance(host, str) or not host):
                raise ValueError
            protocol = entry.get("protocol", "tcp")
        elif isinstance(entry, (str, int)) and not isinstance(entry, bool):
            value = str(entry)
            if "$" in value:
                return None, "Port interpolation is unresolved; local environment values are not read."
            value, sep, suffix = value.partition("/")
            if sep:
                protocol = suffix
            if value.startswith("["):
                match = re.fullmatch(r"\[([^\]]+)\]:([0-9]+):([0-9]+)", value)
                if not match:
                    raise ValueError
                host, pub, target = match.groups()
                published = _port_number(pub)
            else:
                match = re.fullmatch(r"(?:(?:(\d{1,3}(?:\.\d{1,3}){3}):)?([0-9]+):)?([0-9]+)", value)
                if not match:
                    raise ValueError
                host, pub, target = match.groups()
                if pub is not None:
                    published = _port_number(pub)
            target = _port_number(target)
        else:
            raise ValueError
        if protocol not in ("tcp", "udp"):
            raise ValueError
        if host is None:
            binding = "wildcard"
        else:
            if "%" in host:
                raise ValueError
            address = ipaddress.ip_address(host)
            binding = "loopback" if address.is_loopback else "wildcard" if address.is_unspecified else "non-loopback"
        return Port(service_name, target, published, host, protocol, path, line, index, binding), None
    except (ValueError, TypeError):
        return None, "Unsupported port syntax, range, address, protocol, or port number. Use explicit literal values."


def parse_compose(text: str) -> ComposeDocument:
    data, locations = _read_yaml(text)
    services = {}
    for position, (name, config) in enumerate(data["services"].items(), 1):
        service = Service(name=name, alias=f"service-{position}")
        services[name] = service

        def unresolved(field, reason, location=None):
            service.unresolved.append(Unresolved(field, reason, locations.get(location or ("services", name, field))))

        if "include" in data:
            unresolved("include", "Included files are not loaded; effective configuration is unresolved.", ("include",))
        for field in ("extends", "network_mode", "deploy", "provider"):
            if field in config:
                unresolved(field, "This service uses an unsupported composition, networking, or deployment feature.")
        ports = config.get("ports", [])
        if not isinstance(ports, list):
            unresolved("ports", "The ports field must be a list of supported literal declarations.")
        elif len(ports) > 200:
            unresolved("ports", "More than 200 publication entries per service is unsupported.")
        else:
            for index, entry in enumerate(ports):
                line = locations.get(("services", name, "ports", index))
                port, reason = normalize_port(entry, name, index, line)
                if port:
                    service.ports.append(port)
                else:
                    service.unresolved.append(Unresolved(f"ports[{index}]", reason, line))

        networks = config.get("networks", ["default"])
        definitions = data.get("networks", {})
        if not isinstance(definitions, dict):
            unresolved("networks", "Top-level network declarations must be a mapping.")
        elif not isinstance(networks, (list, dict)) or not networks:
            unresolved("networks", "Only non-empty lists or mappings of declared networks are supported.")
        else:
            for network in networks:
                if not isinstance(network, str) or "$" in network:
                    unresolved("networks", "Network interpolation or non-string network names are unsupported.")
                    break
                if network != "default" and network not in definitions:
                    unresolved("networks", "A service references an undeclared network.")
                    continue
                definition = definitions.get(network)
                if definition is None:
                    definition = {}
                attachment = networks[network] if isinstance(networks, dict) else None
                if not isinstance(definition, dict) or set(definition) - {"driver", "internal", "name"}:
                    unresolved("networks", "External networks, driver options, or advanced network settings are unresolved.")
                elif definition.get("driver", "bridge") != "bridge" or "$" in str(definition):
                    unresolved("networks", "Only literal default or bridge network declarations are supported.")
                elif attachment not in (None, {}):
                    unresolved("networks", "Advanced per-service network settings are unresolved.")
                else:
                    service.networks.add(network)
        if service.unresolved:
            # Do not imply known connectivity for an unresolved service.
            service.networks.clear()
    return ComposeDocument(data, services)
