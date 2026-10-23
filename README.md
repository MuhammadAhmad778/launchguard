# LaunchGuard

**Deploy what you intended to expose.**

LaunchGuard compares your intended service access with host-port publication in a Docker Compose file. It highlights mismatches, previews two narrow corrections, and reanalyzes the candidate. Optional AI explains the tradeoffs using only an allowlisted summary.

Built for solo developers and small teams reviewing a single-server Compose deployment. It is a configuration review assistant, not a comprehensive security scanner or a runtime test.

## The problem

A website should be public, its database should have no host-port publication, and its administration interface should bind to loopback. A Compose file can unintentionally publish all three on unspecified host addresses. A generic warning does not capture what the developer intended.

LaunchGuard asks for that intent explicitly and links the mismatch to configuration evidence. It never claims that a published port is actually internet-reachable or that a corrected deployment is secure.

## Run locally

Requires Python 3.11+; developed and tested on Python 3.12. Docker and an API key are **not required**.

```powershell
git clone https://github.com/MuhammadAhmad778/launchguard.git
cd launchguard
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Open `http://127.0.0.1:8501`. The app binds to loopback by default and disables Streamlit usage telemetry. Keep this local MVP local: it has no application authentication and is not hardened for a public shared server.

## Try the demo

1. Select **Load demo configuration**, then **Parse configuration**.
2. Select **Use demo intentions**. This explicit action chooses external access for `web`, application-only for `database`, and host-local for `admin`.
3. Select **Analyze intent**. Expected: **2 mismatches, 0 review items, 0 unresolved conditions, 1 consistent service**.
4. Select the database and admin services, then **Preview correction and reanalyze**.
5. Inspect the sanitized publication diff. Expected: **2 conditions removed, 0 findings remaining**. This is a statement about these checks, not overall security.
6. Download the sanitized report or the candidate YAML. The candidate retains original values and may contain secrets.

The demo uses only a conspicuously fake password. The sample is an analysis fixture, not a production deployment recommendation.

## Access intentions

| Intention | What is checked |
|---|---|
| Application-only | No `ports` publication; this does not prove host/container isolation |
| Host-local | Any supported published ports explicitly bind to loopback |
| External access intended | A non-loopback publication is consistent with the intention; missing publication prompts review for a proxy or tunnel |
| Not specified | The app asks for intent; it does not infer it from an image or name |

`expose` is not host publication or a firewall rule. Conversely, `ports: ["80"]` requests host publication with an automatically selected host port.

## Features

- Bounded, safe YAML parsing with duplicate-key rejection and source-line evidence.
- Short/long port syntax; IPv4/IPv6, TCP/UDP, target-only publication.
- Evidence-linked intent findings and clearly separated unresolved conditions.
- Two deterministic candidate changes: remove a service's `ports`, or change its non-loopback bindings to loopback.
- Reparse/reanalyze each candidate and compare unrelated parsed values.
- Privacy-safe publication diff and deterministic Markdown report.
- Optional Google Gen AI explanation with inspectable payload and graceful fallback.
- Stale results are invalidated when source, intent, or correction selection changes.

## Rule reference

| ID | Category | Condition |
|---|---|---|
| LG001 | Mismatch | Application-only service has supported host publication |
| LG002 | Mismatch | Host-local intention with unspecified/wildcard host binding |
| LG003 | Mismatch | Host-local intention with a non-loopback explicit address |
| LG004 | Review | External intention without a supported non-loopback publication |
| LG005 | Unresolved | Relevant syntax, interpolation, network, or composition feature is unsupported |
| LG006 | Review | Access intent was not selected |

For a service with unresolved relevant configuration, ordinary consistency judgments and automatic corrections are withheld. Other supported services can still be reviewed. No arbitrary security scores are assigned.

## Scope and limitations

Supported examples include `"8080:80"`, `"127.0.0.1:8080:80"`, `"[::1]:8080:80"`, `"5353:53/udp"`, target-only ports, and long-form `target`, `published`, `host_ip`, and `protocol`. Long-form `name` and `app_protocol` are retained but not interpreted.

The parser accepts one file, at most 100 KB, 50 services, 200 port entries per service, 30 levels of nesting, and 12,000 YAML parsing events. YAML aliases, anchors, merge keys, explicit tags, multiple documents, and non-string mapping keys are rejected. Scalars use a restricted YAML 1.2-like interpretation to avoid YAML 1.1's surprising date, yes/no, and sexagesimal conversions.

Unresolved: relevant variable interpolation, port ranges, host/service/container network modes, `extends`, `include`, `deploy`, provider-managed services, advanced network attachments, external networks, non-bridge drivers, and custom network driver settings. Override files are never merged. Local environment files are never used to resolve submitted configuration.

Basic default/declared bridge networks can show declared shared-network peers. This does not establish that services can connect or that one depends on another. The app does not validate the entire Compose schema or inspect image metadata, runtime listeners, passwords, authentication, application logic, firewalls, routing, or cloud security groups. An omitted host IP is classified as unspecified/wildcard under the ordinary publication interpretation; daemon defaults and network configuration outside the submitted file remain unknown.

Loopback binding is not a universal isolation guarantee. An application-only correction removes host port publication, not other possible paths of access. External access may be provided through a reverse proxy or tunnel that the app does not model.

## What candidate verification means

Corrections happen in memory. No input file is overwritten and no Docker, shell, or deployment command is executed.

For selected services, the engine either removes the full `ports` field or rewrites non-loopback publications as explicit loopback bindings. IPv6 bindings become `::1`; other supported non-loopback bindings become `127.0.0.1`. Existing loopback entries remain unchanged.

The candidate is serialized, reparsed, and analyzed with the same intent. The engine rejects candidates that introduce new supported findings, leave targeted mismatches unresolved, or change unrelated parsed configuration. Existing unrelated findings may remain and are counted.

Serialization can remove comments and change formatting. The displayed diff is an **allowlisted publication summary**, not the complete source diff. Verification does not establish that the application works, the deployment is secure, or external clients can reach a service.

## Optional AI setup

Copy `.env.example` to `.env` and edit it locally:

```dotenv
GEMINI_API_KEY=your_local_api_key
LAUNCHGUARD_MODEL=an_exact_model_available_to_your_account
```

Do not paste credentials into chat or commit them. `.env` is ignored. No default model or silent model substitution is used. Missing credentials leave deterministic analysis fully operational. The sidebar shows the configured model. Local `.env` settings are reread on each interaction and take precedence over process environment values, so changing a key or model does not require a server restart; blank local settings disable AI.

Click **Explain findings with AI** only when you want an external request. Inspect the exact structured facts first. Requests use Google's official `google-genai` SDK, a 45-second per-request timeout and bounded output. Temporary HTTP 502/503/504 failures are retried once after one second, on the same model (at most two attempts). Quota, authentication, unavailable-model, invalid-response, and client-timeout errors are not automatically retried. Gemini requests use JSON output mode; Gemma uses prompt-based JSON. Some models may return nonconforming responses; those are rejected with a safe message. API/model access must be tested with your own configured account. Model-list access does not guarantee generation access: HTTP 404, quota limits, and provider failures are shown separately. The local integration was verified with `gemini-3.1-flash-lite`; availability can differ by account.

AI text is clearly labeled and rendered as text. It cannot edit deterministic findings or generate/apply executable changes. It can still give inaccurate advice. The downloadable deterministic report excludes AI prose.

## Privacy

- Raw YAML remains in the local app process and your browser session; it is not sent to the model.
- AI receives positional service aliases, intent enums, binding categories, rule IDs, correction types, and fixed verification facts. Names, IP addresses, environment values, labels, commands, images, and raw configuration are excluded.
- Reports and diff previews are created from allowlisted fields, not imperfect regex redaction of a full file.
- Original names appear locally to help you choose intentions. Reports use `service-1`, `service-2`, etc., in input order. Line evidence lets you map aliases back to your input.
- Candidate YAML intentionally retains original configuration values, including any secrets, and is labeled accordingly.
- No raw YAML or provider exception text is logged. Data is not saved to a database. Only files you download persist as artifacts.

## Architecture

```text
Compose YAML → bounded parser → normalized services and ports
                                      + explicit access intentions
                                      ↓
                              deterministic analyzer
                               ↙                ↘
                    findings/report      selected correction
                                                ↓
                                  candidate YAML → reparse/reanalyze

Allowlisted facts only → optional Google model → separate explanation
```

| Module | Responsibility |
|---|---|
| `app.py` | Streamlit interface, workflow, session invalidation |
| `compose_parser.py` | Bounded safe parsing, source locations, port/network interpretation |
| `models.py` | Small dataclasses, intent enum, shared limitations |
| `analyzer.py` | LG001–LG006, consistency classification, shared-network declarations |
| `corrections.py` | Narrow in-memory transformations and candidate validation |
| `reporting.py` | Sanitized evidence report and publication-only diff |
| `ai_client.py` | Allowlisted payload, optional SDK call, response validation, safe errors |

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover IPv4/IPv6 and protocol handling, malformed/unresolved input, duplicate keys and resource limits, intent comparisons, transformations and idempotence, preservation of unrelated values, privacy boundaries, mocked model calls/errors, and the end-to-end Streamlit demo including stale-state invalidation. No tests require API credentials or Docker.

GitHub Actions runs the tests on Python 3.11 and 3.12.

## Three-minute presentation

**0:00–0:30 — The problem.** “I intended to expose a website, but my database and administration interface also publish ports. LaunchGuard compares the configuration against my explicit intention.”

**0:30–1:15 — The evidence.** Load the sample, parse it, choose demo intentions, and analyze. Show the two mismatches and their source lines. Explain that real internet reachability is unknown.

**1:15–2:10 — The correction.** Preview both corrections. Show removal of database publication and the admin binding becoming loopback. Explain which clients may lose access.

**2:10–2:40 — The check.** Show reanalysis and unchanged unrelated configuration. Optional: request an AI explanation or inspect the exact safe payload. The demo still works without a key or network.

**2:40–3:00 — The boundary.** “The targeted configuration conditions are resolved. We did not run containers, test connectivity, or certify security.” Download the sanitized report.

### Likely judge questions

**Why not just use a scanner?** Established scanners are useful. This prototype focuses on explicit developer intent, a small correction preview, and a transparent before/after check. It does not claim broader scanning coverage or unique invention of remediation.

**Why AI?** To explain operational consequences and questions to confirm. Detection and changes remain deterministic; the app still works without the model.

**Can the fix break something?** Yes. Removing host publication can break host/external clients, and changing a binding can remove access through other interfaces. The user reviews the candidate; there is no automatic deployment.

**What has actually been verified?** Supported syntax, the targeted conditions, and preservation of unrelated parsed fields. Runtime behavior remains untested.

**What would you measure with real users?** Time to choose an appropriate correction, correctness of that decision, understanding of access consequences, and performance compared with scanner output plus a general AI explanation.

## Future work

Validate the workflow with real Compose users before broadening scope. Potential next steps: override-file interpretation, CLI/pre-commit integration, comment-preserving edits, and explicitly authorized runtime checks. This MVP intentionally does not add Kubernetes, Terraform, cloud-account access, or automatic deployment.

## References

- [Docker Compose services and ports](https://docs.docker.com/reference/compose-file/services/#ports)
- [Docker port publishing](https://docs.docker.com/engine/network/port-publishing/)
- [Compose networking](https://docs.docker.com/compose/how-tos/networking/)
- [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/)

## License

MIT. See [LICENSE](LICENSE).
