"""Reports/diffs are allowlisted projections, never redactions of complete YAML."""
import difflib
import json

from models import LIMITS


def publication_projection(document):
    result = {}
    for service in document.services.values():
        result[service.alias] = {
            "ports": [{"target": p.target_port, "published": p.published_port,
                       "binding": p.binding, "protocol": p.protocol}
                      for p in service.ports],
            "unresolved_conditions": len(service.unresolved),
        }
    return result


def safe_diff(before, after):
    left = json.dumps(publication_projection(before), indent=2).splitlines()
    right = json.dumps(publication_projection(after), indent=2).splitlines()
    return "\n".join(difflib.unified_diff(left, right, fromfile="original-publication-summary",
                                        tofile="candidate-publication-summary", lineterm="")) or "No publication changes."


def make_report(document, analysis, candidate=None):
    lines = ["# LaunchGuard configuration review", "", "Service names are pseudonymized; raw configuration is excluded.",
             "", "## Findings"]
    if not analysis.findings:
        lines.append("No mismatches or review conditions detected within the supported scope. This is not a security certification.")
    for f in analysis.findings:
        alias = document.services[f.service_name].alias
        lines += [f"\n### {f.rule_id} — {alias}: {f.title}",
                  f"Category: {f.category}. Intent: {f.intended_access}.",
                  f"Evidence: `{f.evidence_path}`" + (f" (line {f.line_number})" if f.line_number else ""),
                  f.observed_configuration, f.explanation, "Suggested action: " + f.suggested_action,
                  "Assumption: " + " ".join(f.assumptions)]
    if analysis.consistent_services:
        lines += ["\nConsistent with stated publication intent: " + ", ".join(
            document.services[name].alias for name in analysis.consistent_services)]
    if candidate:
        lines += ["\n## Candidate reanalysis", "Targeted configuration mismatch resolved in the candidate.",
                  f"Conditions removed: {candidate.removed_findings}. Remaining findings: {len(candidate.analysis.findings)}.",
                  "Unrelated parsed fields were checked for semantic equality.",
                  "```diff", safe_diff(document, candidate.document), "```"]
    lines += ["\n## Verification limits", *["- " + item for item in LIMITS],
              "- Loopback binding is not a universal isolation guarantee.",
              "- Shared network declarations do not prove connectivity or an application dependency.",
              "- AI advice is separate and is excluded from this deterministic report."]
    return "\n\n".join(lines)
