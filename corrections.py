"""Two constrained transformations, followed by independent parsing and reanalysis."""
from copy import deepcopy

import yaml

from analyzer import analyze
from compose_parser import parse_compose
from models import Candidate, Intent


class CorrectionError(ValueError):
    pass


def propose(document, intents, selected_services):
    selected = list(dict.fromkeys(selected_services))
    if not selected or any(name not in document.services for name in selected):
        raise CorrectionError("Select at least one supported service.")
    before = analyze(document, intents)
    changed = deepcopy(document.data)
    for name in selected:
        service = document.services[name]
        if service.unresolved:
            raise CorrectionError("Automatic corrections are unavailable for unresolved services.")
        intent = intents.get(name)
        if intent == Intent.APPLICATION:
            changed["services"][name].pop("ports", None)
        elif intent == Intent.LOCAL:
            for port in service.ports:
                if port.binding == "loopback":
                    continue
                original = changed["services"][name]["ports"][port.index]
                replacement = deepcopy(original) if isinstance(original, dict) else {
                    "target": port.target_port, "protocol": port.protocol,
                }
                if port.published_port is not None and not isinstance(original, dict):
                    replacement["published"] = str(port.published_port)
                replacement["host_ip"] = "::1" if port.host_ip and ":" in port.host_ip else "127.0.0.1"
                changed["services"][name]["ports"][port.index] = replacement
        else:
            raise CorrectionError("Only application-only and host-local corrections are supported.")
    text = yaml.safe_dump(changed, sort_keys=False, allow_unicode=True, width=100)
    candidate = parse_compose(text)
    # Compare the complete semantic tree except explicitly selected ports fields.
    original_rest = deepcopy(document.data)
    candidate_rest = deepcopy(candidate.data)
    for name in selected:
        original_rest["services"][name].pop("ports", None)
        candidate_rest["services"][name].pop("ports", None)
    if original_rest != candidate_rest:
        raise CorrectionError("Candidate rejected: unrelated configuration changed during serialization.")
    after = analyze(candidate, intents)
    signature = lambda f: (f.service_name, f.rule_id, f.port_index)
    prior = {signature(f) for f in before.findings}
    if any(signature(f) not in prior for f in after.findings):
        raise CorrectionError("Candidate rejected: reanalysis found a new condition.")
    if any(f.service_name in selected and f.category in ("Mismatch", "Unresolved") for f in after.findings):
        raise CorrectionError("Candidate rejected: a targeted mismatch remains unresolved.")
    return Candidate(text, candidate, after, selected, len(before.findings) - len(after.findings))
