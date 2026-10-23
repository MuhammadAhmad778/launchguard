---
name: launchguard
description: Run, maintain, and explain LaunchGuard, the Streamlit Docker Compose deployment-intent checker. Use for LaunchGuard configuration reviews, correction previews, UI changes, AI integration troubleshooting, and deployment maintenance.
---

# LaunchGuard

Work from the LaunchGuard repository root. This skill documents the existing application; it does not provide a standalone scanner or grant permission to change a user's infrastructure.

## Purpose and boundaries

Compare explicit service-access intentions against host-port publication in one Docker Compose file. Keep detection and correction deterministic. Use AI only to explain allowlisted facts and operational tradeoffs.

Ask for missing access intentions instead of inferring them from service names or images:

| Intention | Expected configuration |
| --- | --- |
| Application-only | No host publication through `ports` |
| Host-local | Supported publications bind explicitly to loopback |
| External access intended | Supported non-loopback publication, or review an unmodeled proxy/tunnel |
| Not specified | Request an intention; do not assume one |

These checks do not establish internet reachability, container isolation, working authentication, or overall security. `expose` is not a firewall rule. Declared shared networks do not prove connectivity. Do not execute submitted Compose files or deploy candidate corrections as part of a review.

## Review workflow

1. Parse the submitted YAML with `compose_parser.py`. Preserve bounded parsing and unresolved-condition handling; do not substitute unrestricted YAML loading.
2. Collect an explicit intention for each service and analyze with `analyzer.py`.
3. Separate mismatches, review items, unresolved conditions, and consistent services. Present rule IDs, source evidence, assumptions, and limits.
4. For selected supported mismatches, use `corrections.py` to preview removal of host publication or conversion to loopback. Explain which clients may lose access.
5. Reparse and reanalyze the candidate with the same intentions. Preserve the engine's checks for new findings, targeted mismatches, and unrelated parsed values.
6. Offer the sanitized report and, separately, candidate YAML. Candidate YAML retains original values and may contain secrets; serialization may change formatting and remove comments.

For the built-in demo, explicitly apply demo intentions before analysis. Expect two mismatches and one consistent service. Correcting both mismatches should remove two conditions and leave zero findings within the supported checks—not certify security.

## Find the implementation

| File | Responsibility |
| --- | --- |
| `app.py` | Three-stage Streamlit workflow and session-state invalidation |
| `ui_components.py` | Service, finding, publication, and topology presentation |
| `ui.css`, `dark.css` | Shared styling and dark-theme tokens |
| `models.py` | Intent enum and shared data structures |
| `compose_parser.py` | Safe parsing, limits, normalized ports, source evidence |
| `analyzer.py` | Rules LG001–LG006 and consistency classifications |
| `corrections.py` | In-memory candidate transformations and validation |
| `reporting.py` | Allowlisted reports and publication diffs |
| `ai_client.py` | Settings, safe payload, model requests, validated explanations |

Read `README.md` for detailed syntax coverage and rule definitions. Read `DESIGN.md` before interface changes. Preserve native keyboard controls, light/dark readability, confirmation for destructive input replacement, and invalidation of stale analysis when inputs change.

## Run and verify

Use Python 3.12 and install `requirements.txt` in a virtual environment. On Windows:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

On macOS/Linux use `.venv/bin/python` instead. Tests do not need Docker or API credentials. For behavioral changes, run relevant tests; for UI changes, also exercise parse, intention selection, analysis, correction preview, back navigation, and downloads. Do not describe mocked AI tests as live model verification.

## Optional AI

Configure `GEMINI_API_KEY` and `LAUNCHGUARD_MODEL` through environment variables or an ignored local `.env`. Use an exact model available to the account; do not silently substitute models. Configuration alone does not prove generation works.

Send only the payload produced by `ai_client.build_payload`: aliases, intention enums, binding categories, rule IDs, correction types, and fixed verification facts. Never add raw YAML, service names, IP addresses, images, environment values, or credentials. Keep AI prose separate from deterministic results. Provider failure must leave analysis and candidate results available.

## Deployment maintenance

The repository is https://github.com/MuhammadAhmad778/launchguard. Streamlit Community Cloud uses branch `main`, entrypoint `app.py`, and Python 3.12. Configure AI credentials as root-level entries in the host's Secrets settings, never in tracked files.

The user-provided deployment address is https://launchguard-cbjxuyjpqdrjzugb7qfasp.streamlit.app/. Verify its current health before claiming deployment success. Hosted submissions are processed on the hosting server; do not describe them as remaining solely on the user's computer.

Push or redeploy only within the user's requested scope. Keep `.env`, `.streamlit/secrets.toml`, and generated candidate files out of Git. An authorized push to the connected branch may trigger a cloud rebuild; distinguish a successful push from a verified healthy deployment.
