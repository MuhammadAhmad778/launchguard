"""LaunchGuard's local review workflow. Business logic lives in separate modules."""
import hashlib
from pathlib import Path

import streamlit as st

from ai_client import AIError, build_payload, explain, read_settings
from analyzer import analyze, shared_networks
from compose_parser import ComposeError, parse_compose
from corrections import CorrectionError, propose
from models import Intent, LIMITS
from reporting import make_report, safe_diff

ROOT = Path(__file__).resolve().parent
ai_settings = read_settings(ROOT / ".env")
SAMPLE = (ROOT / "samples" / "demo-compose.yaml").read_text(encoding="utf-8")

st.set_page_config(page_title="LaunchGuard · Deployment intent", page_icon="◈", layout="wide")
st.markdown("""<style>
.block-container {max-width:1260px;padding-top:2.3rem;padding-bottom:4rem}
h1 {letter-spacing:-.055em;font-size:3.4rem !important;font-weight:750 !important}
h2 {letter-spacing:-.025em}
[data-testid="stMetric"] {background:#fff;border:1px solid #dde5ec;border-radius:14px;padding:16px}
[data-testid="stTextArea"] textarea {font-family:Consolas,monospace;font-size:13px}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:14px}
.eyebrow {color:#087f8c;font-size:12px;font-weight:750;letter-spacing:.18em;margin-bottom:8px}
.subhead {font-size:18px;color:#516173;max-width:760px;line-height:1.6;margin-bottom:22px}
.quiet {color:#64748b;font-size:13px}
</style>""", unsafe_allow_html=True)  # Static styling only. Never interpolate user content.


def clear_results():
    for key in ("analysis", "candidate", "ai_result", "ai_error", "correction_selection"):
        st.session_state.pop(key, None)


def clear_input():
    clear_results()
    st.session_state.pop("document", None)
    for key in list(st.session_state):
        if key.startswith("intent_"):
            del st.session_state[key]


def clear_candidate():
    for key in ("candidate", "ai_result", "ai_error"):
        st.session_state.pop(key, None)


def load_sample():
    clear_input()
    st.session_state["editor"] = SAMPLE


with st.sidebar:
    st.markdown("### ◈ LaunchGuard")
    st.caption("DEPLOYMENT INTENT REVIEW")
    st.divider()
    st.markdown("**01**  Inspect your configuration\n\n**02**  Declare access intent\n\n**03**  Review a correction")
    st.divider()
    st.markdown("**Local analysis**")
    st.caption("Your configuration stays in this app process. AI receives only pseudonymized, allowlisted facts when you request it.")
    enabled = ai_settings.configured
    st.caption("AI explanation configured" if enabled else "Deterministic-only mode · no API key required")
    if enabled:
        st.text("Model: " + ai_settings.model)
    st.divider()
    st.caption("Single-file Docker Compose review. Nothing is deployed or executed.")

st.markdown('<div class="eyebrow">CONFIGURATION → INTENT → REVIEWABLE CHANGE</div>', unsafe_allow_html=True)
st.title("Deploy what you intended to expose.")
st.markdown('<div class="subhead">Compare your Compose host-port bindings with the access you intended. Understand the mismatch, preview a correction, and check it again.</div>', unsafe_allow_html=True)

left, right = st.columns([1.55, 1], gap="large")
with left:
    st.subheader("01 / Compose configuration")
    st.button("Load demo configuration", on_click=load_sample)
    source = st.text_area("Compose YAML", key="editor", height=360,
                          placeholder="services:\n  web:\n    image: nginx:stable\n    ports:\n      - \"8080:80\"",
                          on_change=clear_input)
    st.caption("One YAML document · up to 100 KB · 50 services · no execution")
    if st.button("Parse configuration", type="primary", width="stretch"):
        clear_input()
        try:
            st.session_state.document = parse_compose(source)
            st.session_state.source_digest = hashlib.sha256(source.encode()).hexdigest()
        except ComposeError as error:
            st.error(str(error))
with right:
    st.subheader("What does each intention mean?")
    with st.container(border=True):
        st.markdown("**Application-only**")
        st.caption("No host-port publication. This does not establish isolation from the host or other containers.")
        st.markdown("**Host-local**")
        st.caption("Published ports explicitly bind to loopback. Real accessibility still depends on the environment.")
        st.markdown("**External access intended**")
        st.caption("Non-loopback publication may match your intention. A reverse proxy or tunnel may also provide access.")
    st.info("Configured publication is not confirmed reachability. Firewalls, routing, authentication, and running services are outside this review.")

document = st.session_state.get("document")
if document is None:
    st.divider()
    st.caption("Start with the demo: a public website, an application-only database, and a host-local administration service.")
    st.stop()

# A settings edit invalidates old AI text/errors, but keeps deterministic results.
settings_fingerprint = hashlib.sha256((ai_settings.api_key + "\0" + ai_settings.model).encode()).hexdigest()
if st.session_state.get("ai_settings_fingerprint") != settings_fingerprint:
    st.session_state.pop("ai_result", None)
    st.session_state.pop("ai_error", None)
    st.session_state.ai_settings_fingerprint = settings_fingerprint

# Defense against stale results even if the framework callback is skipped.
if hashlib.sha256(source.encode()).hexdigest() != st.session_state.get("source_digest"):
    clear_input()
    st.rerun()

st.divider()
st.subheader("02 / Declare access intent")
st.caption("Choose what each service should expose. Intent is never inferred from its name or image.")
if source == SAMPLE and st.button("Use demo intentions"):
    clear_results()
    demo = {"web": Intent.EXTERNAL, "database": Intent.APPLICATION, "admin": Intent.LOCAL}
    for name, service in document.services.items():
        st.session_state[f"intent_{service.alias}"] = demo[name].value

intents = {}
for name, service in document.services.items():
    with st.container(border=True):
        a, b = st.columns([1, 1.5])
        with a:
            st.text(name)
            st.caption(f"Report identifier: {service.alias}")
            intents[name] = st.selectbox("Intended access", [i.value for i in Intent],
                                         key=f"intent_{service.alias}", on_change=clear_results)
        with b:
            if service.ports:
                st.dataframe([{"Publication": p.description, "Binding": p.binding, "Line": p.source_line}
                              for p in service.ports], hide_index=True, width="stretch")
            else:
                st.caption("No supported host-port entries found.")
            if service.unresolved:
                st.warning(f"{len(service.unresolved)} unresolved condition(s). Automatic correction unavailable.")

if st.button("Analyze intent", type="primary"):
    clear_results()
    st.session_state.analysis = analyze(document, intents)

analysis = st.session_state.get("analysis")
if analysis is None:
    st.stop()

st.divider()
st.subheader("03 / Review your findings")
counts = [sum(f.category == category for f in analysis.findings) for category in ("Mismatch", "Review", "Unresolved")]
for column, title, count in zip(st.columns(4), ["Intent mismatches", "Review items", "Unresolved conditions", "Consistent services"],
                               counts + [len(analysis.consistent_services)]):
    column.metric(title, count)
st.caption("Counts describe this configuration review; they are not a security score.")

for finding in analysis.findings:
    alias = document.services[finding.service_name].alias
    with st.expander(f"{finding.rule_id} · {alias} · {finding.title}", expanded=finding.category == "Mismatch"):
        st.text(f"Category: {finding.category} | Intent: {finding.intended_access}")
        st.code(finding.evidence_path + (f" · line {finding.line_number}" if finding.line_number else ""), language=None)
        st.write(finding.observed_configuration)
        st.write(finding.explanation)
        st.markdown("**Suggested action**")
        st.write(finding.suggested_action)
        st.caption("Assumption: " + " ".join(finding.assumptions))
        st.caption("Unknowns: " + " ".join(finding.unknowns))

if analysis.consistent_services:
    st.success("Consistent with stated publication intent: " + ", ".join(document.services[n].alias for n in analysis.consistent_services))
    st.caption("This does not establish that these services are secure or reachable.")

correctable = list(dict.fromkeys(f.service_name for f in analysis.findings if f.correction_available))
if correctable:
    st.markdown("### Preview a correction")
    selected = st.multiselect("Services to correct", correctable, default=correctable,
                              format_func=lambda name: document.services[name].alias,
                              key="correction_selection", on_change=clear_candidate)
    for name in selected:
        service = document.services[name]
        if intents[name] == Intent.APPLICATION:
            st.write(f"{service.alias}: remove all host publication. Host-port clients and external clients may lose access.")
            peers = shared_networks(document, name)
            st.caption("Declared shared-network peers: " + (", ".join(peers) or "none resolved") +
                       ". Shared declarations do not prove connectivity or application dependencies.")
        else:
            st.write(f"{service.alias}: change non-loopback publications to loopback. Clients using other host interfaces may lose access.")
    st.caption("YAML serialization may change formatting and remove comments. Unrelated parsed values are checked for equality.")
    if st.button("Preview correction and reanalyze", disabled=not selected):
        clear_candidate()
        try:
            st.session_state.candidate = propose(document, intents, selected)
        except (CorrectionError, ComposeError) as error:
            st.error(str(error))

candidate = st.session_state.get("candidate")
if candidate:
    st.success("Targeted configuration mismatch resolved in the candidate.")
    st.write(f"{candidate.removed_findings} condition(s) removed · {len(candidate.analysis.findings)} finding(s) remain")
    st.caption("Candidate reparsed. Analysis rerun with the same intent. Unrelated parsed fields unchanged. No runtime testing performed.")
    st.code(safe_diff(document, candidate.document), language="diff")
    st.caption("Privacy-safe publication diff: only normalized port facts are shown; names, IP addresses, and unrelated configuration are omitted.")
    st.warning("The candidate download retains your original configuration values and may contain secrets. It is not the sanitized report.")
    st.download_button("Download candidate configuration", candidate.text, "candidate-compose.yaml", "application/yaml")

st.divider()
ai_col, report_col = st.columns(2, gap="large")
with ai_col:
    st.subheader("Optional AI explanation")
    st.caption("Only pseudonymized intent, binding categories, rule IDs, and verification facts are sent to Google. Raw YAML and service names are excluded.")
    with st.expander("Inspect the exact facts sent to AI"):
        st.json(build_payload(document, analysis, intents, candidate))
    if st.button("Explain findings with AI"):
        st.session_state.pop("ai_result", None)
        st.session_state.pop("ai_error", None)
        with st.spinner("Requesting an explanation… Temporary provider failures are retried once; this may take up to 90 seconds."):
            try:
                st.session_state.ai_result = explain(build_payload(document, analysis, intents, candidate), settings=ai_settings)
            except AIError as error:
                st.session_state.ai_error = str(error)
    if st.session_state.get("ai_error"):
        st.info(st.session_state.ai_error)
    if st.session_state.get("ai_result"):
        st.caption("AI-generated advice · may be inaccurate · does not replace deterministic findings")
        for field, value in st.session_state.ai_result.items():
            st.markdown("**" + field.replace("_", " ").capitalize() + "**")
            st.text(value if isinstance(value, str) else "\n\n".join(value))
with report_col:
    st.subheader("Take the review with you")
    st.write("Download a sanitized Markdown report with deterministic evidence, correction results, and verification limits.")
    st.download_button("Download sanitized report", make_report(document, analysis, candidate),
                       "launchguard-report.md", "text/markdown")
    with st.expander("What this review does not establish", expanded=True):
        for limitation in LIMITS:
            st.write("• " + limitation)
