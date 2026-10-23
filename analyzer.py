"""Deterministic intent comparisons. Neither network access nor AI is used here."""
from models import Analysis, ComposeDocument, Finding, Intent, LIMITS


def analyze(document: ComposeDocument, intents: dict[str, str]) -> Analysis:
    findings = []
    consistent = []
    for name, service in document.services.items():
        try:
            intent = Intent(intents.get(name, Intent.UNSPECIFIED))
        except ValueError:
            intent = Intent.UNSPECIFIED
        start = len(findings)

        def add(rule, title, category, observed, field, explanation, action, port=None, correct=False, line=None):
            findings.append(Finding(
                rule, name, title, category, intent.value, observed,
                "include" if field == "include" else f"services.{service.alias}.{field}", port.source_line if port else line,
                explanation, ("Single-file Compose host-publication interpretation only.",),
                LIMITS, action, correct and not service.unresolved,
                port.index if port else None,
            ))

        for item in service.unresolved:
            add("LG005", "Relevant configuration is unresolved", "Unresolved", item.reason, item.field,
                "This condition cannot be interpreted reliably within the supported scope.",
                "Expand or simplify the configuration before reviewing an automatic correction.", line=item.line)
        if intent == Intent.UNSPECIFIED:
            add("LG006", "Access intent is missing", "Review", "No access intention selected.", "ports",
                "Service names and images do not establish the developer's intended access.",
                "Choose an access intent for this service.")
            continue
        # A known local fragment must not imply the effective config is resolved.
        if service.unresolved:
            continue
        for port in service.ports:
            field = f"ports[{port.index}]"
            observed = f"{port.binding} binding; host port {port.published_port or 'automatic'} to {port.target_port}/{port.protocol}"
            if intent == Intent.APPLICATION:
                add("LG001", "Host publication conflicts with application-only intent", "Mismatch", observed, field,
                    "A ports entry requests host publication. Removing it does not establish network isolation.",
                    "Remove this service's host publication if host and external clients do not require it.", port, True)
            elif intent == Intent.LOCAL and port.binding != "loopback":
                rule = "LG002" if port.binding == "wildcard" else "LG003"
                add(rule, "Host binding conflicts with host-local intent", "Mismatch", observed, field,
                    "The configured publication is not explicitly loopback-only. Private addresses are not loopback.",
                    "Preview an explicit loopback binding; access through other host interfaces may stop.", port, True)
        if intent == Intent.EXTERNAL and not any(p.binding != "loopback" for p in service.ports):
            add("LG004", "External access path needs review", "Review", "No supported non-loopback publication.", "ports",
                "A reverse proxy or tunnel may provide access outside this analysis; this is not a confirmed failure.",
                "Confirm the intended proxy, tunnel, or publication path. No public port is added automatically.")
        if len(findings) == start:
            consistent.append(name)
    return Analysis(findings, consistent)


def shared_networks(document, name):
    service = document.services[name]
    return {other.alias: len(service.networks & other.networks)
            for key, other in document.services.items()
            if key != name and service.networks & other.networks}
