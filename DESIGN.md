# LaunchGuard interface

## Product and scope
A local Streamlit workflow for developers reviewing a single Docker Compose file before deployment. Its deterministic parser, intent rules, correction pipeline, reports, and AI allowlist remain the source of truth. Configured host publication is not confirmed connectivity or security. AI availability must not be inferred from a configured model name.

## Visual system
Dark-first navy and slate surfaces with cyan primary actions, near-white text, and muted slate secondary text. Light mode uses the same component rules with alternate tokens. `ui.css` owns layout and components; `dark.css` only overrides palette tokens. Spacing follows 8px increments; controls have a 44px minimum hit area. Native inputs retain keyboard behavior and visible focus. No generated framework class selectors, remote font requests, or frontend dependencies are added.

## Workflow
1. Configure: native YAML editor, byte count, parse validation, demo loading, confirmed replacement/reset.
2. Define intent: service identity and publication table beside native radio choices. All choices remain visible. A real specified-intent count reduces memory burden.
3. Analyze and correct: genuine operation status without artificial delays or arbitrary percentages; category counts and evidence-based finding cards; optional publication map; before/after publication tables and diff; reanalysis and downloads.

Back navigation preserves widget values. Editing configuration or intent invalidates downstream results. Re-parsing identical input preserves valid work. Reset/replacement requires inline confirmation. Settings changes invalidate only AI advice, before displaying connection status.

## Information hierarchy
Primary actions use cyan. Categories have text labels as well as color. Detailed evidence, assumptions, candidate YAML, and uncertainty are progressively disclosed; suggested actions and runtime limits remain visible. AI guidance is separate from deterministic facts and uses the actual configured model family in its heading.

## Verification
Automated coverage includes navigation, state invalidation, theme preservation, invalid YAML, reset cancellation/confirmation, explicit reanalysis, provider success/error fixtures, parser/rules/privacy, and corrections. Browser checks cover the demo flow, downloads, dark/light themes and 1440/768/390px layouts. Full assistive-technology certification is outside this verification.
