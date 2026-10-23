"""LaunchGuard's local review workflow. Business logic lives in separate modules."""
import hashlib
import base64
from pathlib import Path

import streamlit as st

from ai_client import AIError, build_payload, explain, read_settings
from analyzer import analyze, shared_networks
from compose_parser import ComposeError, parse_compose
from corrections import CorrectionError, propose
from models import Intent, LIMITS
from reporting import make_report, safe_diff
from ui_components import badge, section, publication, service_heading, finding_card, publication_map, INTENT_HELP

ROOT = Path(__file__).resolve().parent
ai_settings = read_settings(ROOT / ".env")
SAMPLE = (ROOT / "samples" / "demo-compose.yaml").read_text(encoding="utf-8")

st.set_page_config(page_title="LaunchGuard · Deployment intent", page_icon=str(ROOT / "assets" / "launchguard.png"), layout="wide")




def clear_results():
    for key in ("analysis", "candidate", "ai_result", "ai_error", "correction_selection", "topology_service"):
        st.session_state.pop(key, None)


def clear_input():
    st.session_state.step = 1
    clear_results()
    st.session_state.pop("document", None)
    for key in list(st.session_state):
        if key.startswith("intent_"):
            del st.session_state[key]


def clear_candidate():
    for key in ("candidate", "ai_result", "ai_error"):
        st.session_state.pop(key, None)


def replace_editor(value):
    clear_input()
    st.session_state["editor"] = value
    st.session_state.pop("pending_replace", None)


def load_sample():
    if st.session_state.get("editor", "").strip() and st.session_state.editor != SAMPLE:
        st.session_state.pending_replace = "sample"
    else:
        replace_editor(SAMPLE)


def request_reset():
    st.session_state.pending_replace = "reset"



# Retain widget values when their screen is not rendered.
for widget_key in list(st.session_state):
    if widget_key == "editor" or widget_key.startswith("intent_") or widget_key == "correction_selection":
        st.session_state[widget_key] = st.session_state[widget_key]
st.session_state.setdefault("step", 1)
step = st.session_state.step
source = st.session_state.get("editor", "")

def go_to(step_number):
    st.session_state.step = step_number

# A settings edit invalidates old AI text/errors, but keeps deterministic results.
settings_fingerprint = hashlib.sha256((ai_settings.api_key + "\0" + ai_settings.model).encode()).hexdigest()
if st.session_state.get("ai_settings_fingerprint") != settings_fingerprint:
    st.session_state.pop("ai_result", None)
    st.session_state.pop("ai_error", None)
    st.session_state.ai_settings_fingerprint = settings_fingerprint

with st.sidebar:
    st.image(str(ROOT / "assets" / "launchguard.png"), width=56)
    st.markdown("### LaunchGuard")
    st.caption("Compose review workspace")
    dark_mode = st.toggle("Dark mode", value=True, key="dark_mode")

    st.divider()
    st.markdown("**Your review**")
    st.button("1 · Configuration", on_click=go_to, args=(1,), width="stretch")
    st.button("2 · Access intent", on_click=go_to, args=(2,), disabled="document" not in st.session_state, width="stretch")
    st.button("3 · Findings", on_click=go_to, args=(3,), disabled="analysis" not in st.session_state, width="stretch")
    doc = st.session_state.get("document")
    st.caption(f"Configuration parsed · {len(doc.services)} services" if doc else "Configuration not parsed")
    st.caption("Analysis complete" if "analysis" in st.session_state else "Analysis not run")
    if "candidate" in st.session_state:
        st.caption("Candidate reanalyzed · preview only")
    st.button("Reset review", on_click=request_reset, width="stretch", disabled=not source)
    st.divider()
    st.markdown("**AI guidance**")
    if st.session_state.get("ai_result"):
        st.caption("Response received for this review")
    elif st.session_state.get("ai_error"):
        st.caption("Last request failed · local review available")
    else:
        st.caption("Configured · connection not verified" if ai_settings.configured else "Not configured · optional")
    if ai_settings.model:
        st.text(ai_settings.model)
    st.divider()
    st.caption("Analysis runs locally in this app process. AI receives only allowlisted facts when requested. Nothing is deployed.")

css = (ROOT / "ui.css").read_text(encoding="utf-8")
if dark_mode:
    css += "\n" + (ROOT / "dark.css").read_text(encoding="utf-8")
st.markdown("<style>" + css + "</style>", unsafe_allow_html=True)

if st.session_state.get("pending_replace"):
    sample_requested = st.session_state.pending_replace == "sample"
    with st.container(border=True):
        st.warning("Replace the current configuration and clear this review?" if sample_requested else "Clear your configuration, intentions, findings, and AI guidance?")
        confirm, cancel = st.columns(2)
        confirm.button("Confirm replacement" if sample_requested else "Confirm reset", type="primary",
                       on_click=replace_editor, args=(SAMPLE if sample_requested else "",))
        cancel.button("Keep current review", on_click=lambda: st.session_state.pop("pending_replace", None))


brand_image = base64.b64encode((ROOT / "assets" / "launchguard.png").read_bytes()).decode("ascii")
titles = {1: ("Configure your review", "Start with a Compose file. Make access intentions explicit before deployment."),
          2: ("Define access intent", "Decide who should access each service. LaunchGuard will compare the configuration."),
          3: ("Analyze & correct", "Review configuration facts, inspect the change, and check the candidate.")}
st.markdown('<div class="brand-header"><img src="data:image/png;base64,' + brand_image + '" alt="LaunchGuard" width="48" height="48"><div><h1>' + titles[step][0] + '</h1><p>' + titles[step][1] + '</p></div></div>', unsafe_allow_html=True)
# These fixed labels reflect session state; no YAML or provider output enters HTML.
steps = [("1", "Configuration", True),
         ("2", "Access intent", "document" in st.session_state),
         ("3", "Findings & correction", "analysis" in st.session_state)]
st.markdown('<ol class="workflow" aria-label="Review progress">' + ''.join(
    '<li class="' + ('active' if int(number) == step else 'ready' if ready else 'pending') + '"><span>' + number +
    '</span>' + label + (' · Done' if int(number) < step else '') + '</li>' for number, label, ready in steps) + '</ol>', unsafe_allow_html=True)

if step == 1:
    st.caption("Single-file Docker Compose review · No deployment or execution")
    left, right = st.columns([1.8, 1], gap="large")
    with left, st.container(border=True, key="configuration_panel"):
        section("Review your deployment configuration", "Paste your Compose YAML or explore the three-service demo.")
        demo_action, clear_action = st.columns([1.4, 1])
        demo_action.button("Load demo configuration", on_click=load_sample, width="stretch", help="Load a website, database, and admin service to explore the review.")
        clear_action.button("Clear editor", on_click=request_reset, width="stretch", disabled=not source, help="Requires confirmation before clearing your review.")
        source = st.text_area("Compose YAML", key="editor", height=320,
                              placeholder="services:\n  web:\n    image: nginx:stable\n    ports:\n      - \"8080:80\"",
                              on_change=clear_input)
        st.caption(f"{len(source.encode('utf-8')):,} / 100,000 bytes · YAML · Up to 50 services")
        if not source.strip():
            st.caption("Add YAML or load the demo to enable parsing.")
        if st.button("Parse configuration", type="primary", width="stretch", disabled=not source.strip()):
            # Re-entering unchanged YAML preserves valid intent and review results.
            if "document" in st.session_state and hashlib.sha256(source.encode()).hexdigest() == st.session_state.get("source_digest"):
                st.session_state.step = 2
                st.rerun()
            clear_input()
            try:
                with st.spinner("Validating Compose configuration…"):
                    st.session_state.document = parse_compose(source)
                st.session_state.source_digest = hashlib.sha256(source.encode()).hexdigest()
                st.session_state.step = 2
                st.rerun()
            except ComposeError as error:
                st.error(str(error))
                st.caption("Edit the YAML above and parse again. Your input has been preserved.")
    with right:
        st.subheader("Access guide")
        with st.container(border=True):
            st.markdown("**Application-only**")
            st.caption("No host-port publication. This does not establish isolation from the host or other containers.")
            st.markdown("**Host-local**")
            st.caption("Published ports explicitly bind to loopback. Real accessibility still depends on the environment.")
            st.markdown("**External access intended**")
            st.caption("Non-loopback publication may match your intention. A reverse proxy or tunnel may also provide access.")
        st.info("Configured publication is not confirmed reachability. Firewalls, routing, authentication, and running services are outside this review.")
    st.stop()

document = st.session_state.get("document")
if document is None:
    st.divider()
    st.caption("Start with the demo: a public website, an application-only database, and a host-local administration service.")
    st.stop()

# Defense against stale results even if the framework callback is skipped.
if hashlib.sha256(source.encode()).hexdigest() != st.session_state.get("source_digest"):
    clear_input()
    st.rerun()

intents = {name: st.session_state.get(f"intent_{service.alias}", Intent.UNSPECIFIED.value)
           for name, service in document.services.items()}
if step == 2:
    st.button("Back to configuration", on_click=go_to, args=(1,))
    section("Declared service access", f"Configuration parsed successfully: {len(document.services)} services detected.")
    st.caption("Choose what each service should expose. Intent is never inferred from its name or image.")
    if source == SAMPLE and st.button("Use demo intentions"):
        clear_results()
        demo = {"web": Intent.EXTERNAL, "database": Intent.APPLICATION, "admin": Intent.LOCAL}
        for name, service in document.services.items():
            st.session_state[f"intent_{service.alias}"] = demo[name].value

    specified = sum(st.session_state.get(f"intent_{service.alias}", Intent.UNSPECIFIED) != Intent.UNSPECIFIED for service in document.services.values())
    st.markdown('<div class="selection-status">' + badge(f"{specified} of {len(document.services)} intentions specified", "accent") + '<span>Unspecified intentions produce review findings.</span></div>', unsafe_allow_html=True)
    intents = {}
    for name, service in document.services.items():
        with st.container(border=True, key=f"service_card_{service.alias}"):
            a, b = st.columns([1, 1.25], gap="large")
            with a:
                service_heading(name, service.alias, (document.data["services"][name] or {}).get("image"))
                st.caption(f"{len(service.ports)} supported port publication(s)")
            with b:
                publication(service)
            intents[name] = st.radio("Intended access", [i.value for i in Intent], horizontal=True,
                                    key=f"intent_{service.alias}", on_change=clear_results)
            st.caption(INTENT_HELP[intents[name]])
            if service.unresolved:
                st.warning(f"{len(service.unresolved)} unresolved condition(s). Automatic correction unavailable.")
                with st.expander("Unsupported configuration details"):
                    for condition in service.unresolved:
                        st.write(condition.reason)


    if st.button("Analyze intent", type="primary"):
        clear_results()
        with st.status("Reviewing your configuration…", expanded=True) as status:
            st.write(f"Inspecting published ports across {len(document.services)} services…")
            st.write("Comparing configured publication with your access intent…")
            st.session_state.analysis = analyze(document, intents)
            st.write("Preparing findings and available correction actions…")
            status.update(label="Review complete", state="complete", expanded=False)
        st.session_state.step = 3
        st.rerun()
    st.stop()

st.button("Edit access intentions", on_click=go_to, args=(2,))

analysis = st.session_state.get("analysis")
if analysis is None:
    st.stop()

st.divider()
section("Configuration review", f"{len(document.services)} services analyzed · Verified configuration facts, not runtime security checks")
counts = [sum(f.category == category for f in analysis.findings) for category in ("Mismatch", "Review", "Unresolved")]
for column, title, count in zip(st.columns(4), ["Intent mismatches", "Review items", "Unresolved conditions", "Consistent services"],
                               counts + [len(analysis.consistent_services)]):
    column.metric(title, count)
st.caption("Counts describe this configuration review; they are not a security score.")
if counts[0]:
    st.warning(f"{counts[0]} intent mismatch(es) need attention. Review the evidence below, then preview a correction.")
elif not analysis.findings:
    st.success("No publication mismatches found for the intentions you selected.")

publication_map(document, analysis, intents, shared_networks)
for index, finding in enumerate(analysis.findings):
    finding_card(finding, document.services[finding.service_name].alias, key_prefix=str(index))

if analysis.consistent_services:
    st.success("Consistent with stated publication intent: " + ", ".join(document.services[n].alias for n in analysis.consistent_services))
    st.caption("This does not establish that these services are secure or reachable.")

correctable = list(dict.fromkeys(f.service_name for f in analysis.findings if f.correction_available))
if correctable:
    section("Correction workspace", "Preview only. Changes are never applied to your files or environment.")
    st.session_state.setdefault("correction_selection", correctable)
    selected = st.multiselect("Services to correct", correctable,
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
            with st.spinner("Building candidate and checking it against the same intentions…"):
                st.session_state.candidate = propose(document, intents, selected)
            st.rerun()
        except (CorrectionError, ComposeError) as error:
            st.error(str(error))

candidate = st.session_state.get("candidate")
if candidate:
    st.success("Targeted configuration mismatch resolved in the candidate.")
    st.write(f"{candidate.removed_findings} condition(s) removed · {len(candidate.analysis.findings)} finding(s) remain")
    st.caption("Candidate reparsed. Analysis rerun with the same intent. Unrelated parsed fields unchanged. No runtime testing performed.")
    before, after = st.columns(2)
    with before:
        with st.container(border=True):
            st.markdown("**Original configuration**")
            st.write(f"{len(analysis.findings)} finding(s)")
            st.caption("The configuration you supplied.")
            for name in candidate.affected_services:
                st.text(document.services[name].alias)
                publication(document.services[name])
    with after:
        with st.container(border=True):
            st.markdown("**Reanalyzed candidate**")
            st.write(f"{len(candidate.analysis.findings)} finding(s) remain")
            st.caption(f"{candidate.removed_findings} targeted condition(s) removed.")
            for name in candidate.affected_services:
                st.text(candidate.document.services[name].alias)
                publication(candidate.document.services[name])
    if st.button("Reanalyze candidate"):
        try:
            with st.spinner("Reparsing and reanalyzing the candidate…"):
                # Reuse the same guarded correction pipeline and unchanged intentions.
                st.session_state.candidate = propose(document, intents, candidate.affected_services)
            st.rerun()
        except (CorrectionError, ComposeError) as error:
            st.error(str(error))
    with st.expander("Inspect publication diff", expanded=True):
        st.code(safe_diff(document, candidate.document), language="diff")
    if candidate.analysis.findings:
        with st.expander(f"Remaining candidate findings ({len(candidate.analysis.findings)})", expanded=True):
            for remaining in candidate.analysis.findings:
                st.text(f"{remaining.rule_id} · {remaining.category} · {candidate.document.services[remaining.service_name].alias}")
                st.write(remaining.explanation)
    with st.expander("Inspect candidate YAML · contains original values"):
        st.caption("This local preview may contain secrets. It is never sent to AI.")
        st.code(candidate.text, language="yaml")
    st.caption("Privacy-safe publication diff: only normalized port facts are shown; names, IP addresses, and unrelated configuration are omitted.")
    st.warning("The candidate download retains your original configuration values and may contain secrets. It is not the sanitized report.")
    st.download_button("Download candidate configuration", candidate.text, "candidate-compose.yaml", "application/yaml", on_click="ignore")

st.divider()
ai_col, report_col = st.columns(2, gap="large")
with ai_col, st.container(border=True, key="guidance_panel"):
    st.subheader("Gemma 4 — Deployment Guidance" if ai_settings.model.removeprefix("models/").startswith("gemma-4-") else "AI — Deployment Guidance")
    st.markdown(badge("AI-generated operational guidance", "accent"), unsafe_allow_html=True)
    st.caption("Optional advice. Deterministic findings remain authoritative.")
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
        (st.warning if ai_settings.configured else st.info)(st.session_state.ai_error)
        st.caption("Your review is saved in this session. You can retry the explanation or download the report.")
    if st.session_state.get("ai_result"):
        st.caption("AI-generated advice · may be inaccurate · does not replace deterministic findings")
        for field, value in st.session_state.ai_result.items():
            st.markdown("**" + field.replace("_", " ").capitalize() + "**")
            if isinstance(value, str):
                st.text(value)
            else:
                for item in value:
                    st.text("• " + item)
with report_col, st.container(border=True, key="report_panel"):
    st.subheader("Take the review with you")
    st.write("Download a sanitized Markdown report with deterministic evidence, correction results, and verification limits.")
    st.download_button("Download sanitized report", make_report(document, analysis, candidate),
                       "launchguard-report.md", "text/markdown", on_click="ignore")
    with st.expander("What this review does not establish"):
        for limitation in LIMITS:
            st.write("• " + limitation)
