"""Presentation helpers. Untrusted names and text are always HTML-escaped."""
from html import escape
import streamlit as st

INTENT_HELP = {
    "Application-only": "Do not publish this service's ports on the Docker host.",
    "Host-local": "Published ports should explicitly bind to loopback.",
    "External access intended": "Access from outside the host is intended; actual reachability is unknown.",
    "Not specified": "No access requirement declared. Analysis will request a review instead of guessing.",
}


def badge(label, kind="neutral"):
    kind = kind if kind in {"neutral", "success", "warning", "error", "accent"} else "neutral"
    return f'<span class="badge {kind}">{escape(str(label))}</span>'


def section(title, description=""):
    st.header(title)
    if description:
        st.caption(description)


def publication(service):
    """A native HTML table avoids a white canvas inside dark service cards."""
    if not service.ports:
        st.caption("No supported host-port entries found." if service.unresolved else "No host ports published in this file.")
        return
    rows = ''.join('<tr><td><code>' + escape(str(p.published_port or 'Automatic')) +
                   '</code></td><td><code>' + escape(str(p.target_port)) + '/' + escape(p.protocol) +
                   '</code></td><td>' + escape(p.binding) + '</td></tr>' for p in service.ports)
    st.markdown('<div class="table-scroll"><table class="publication-table"><caption>Configured host publication</caption>'
                '<thead><tr><th scope="col">Host port</th><th scope="col">Container</th><th scope="col">Binding</th></tr></thead>'
                '<tbody>' + rows + '</tbody></table></div>', unsafe_allow_html=True)


def service_heading(name, alias, image=None):
    st.markdown('<div class="service-heading"><h3>' + escape(name) + '</h3>' + badge(alias) + '</div>', unsafe_allow_html=True)
    if isinstance(image, str):
        st.markdown('<p class="image-reference">Image <code>' + escape(image) + '</code></p>', unsafe_allow_html=True)


def finding_card(finding, alias, key_prefix="finding"):
    kind = {"Mismatch": "error", "Review": "warning", "Unresolved": "accent"}.get(finding.category, "neutral")
    with st.container(border=True, key=f"finding_{key_prefix}"):
        st.markdown('<div class="finding-heading">' + badge(finding.category, kind) + badge(finding.rule_id) +
                    '<span>' + escape(alias) + '</span></div>', unsafe_allow_html=True)
        st.markdown('<h3 class="finding-title">' + escape(finding.title) + '</h3>', unsafe_allow_html=True)
        st.text("Service: " + finding.service_name)
        st.caption("Declared intent: " + finding.intended_access)
        st.write(finding.observed_configuration)
        st.write(finding.explanation)
        st.markdown("**Suggested action**")
        st.write(finding.suggested_action)
        st.caption("Correction preview available" if finding.correction_available else "Manual review required; no supported automatic correction.")
        with st.expander("Evidence, assumptions & unknowns"):
            st.code(finding.evidence_path + (f" · line {finding.line_number}" if finding.line_number else ""), language=None)
            st.write("Assumptions: " + " ".join(finding.assumptions))
            st.write("Unknowns: " + " ".join(finding.unknowns))


def publication_map(document, analysis, intents, shared_networks):
    with st.expander("Explore service publication"):
        names = list(document.services)
        name = st.selectbox("Inspect a service", names, format_func=lambda n: document.services[n].alias,
                            key="topology_service")
        service = document.services[name]
        st.text(name)
        st.caption("Declared intent: " + str(intents[name]))
        publication(service)
        findings = [f for f in analysis.findings if f.service_name == name]
        state = "Review required" if findings else "Consistent with stated publication intent"
        st.markdown('<div class="publication-flow"><div><strong>Docker host</strong><span>' +
                    str(len(service.ports)) + ' parsed publication(s)</span></div><span aria-hidden="true">→</span>' +
                    '<div><strong>' + escape(service.alias) + '</strong><span>' + escape(state) + '</span></div></div>', unsafe_allow_html=True)
        peers = shared_networks(document, name)
        st.caption("Declared shared-network peers: " + (", ".join(peers) or "none resolved"))
        st.caption("This shows configuration declarations, not traffic or confirmed connectivity. Actual reachability is unknown.")
