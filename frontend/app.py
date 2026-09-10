"""A restrained but modern Streamlit interface for the goonai demonstration."""

from __future__ import annotations

import html
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import streamlit as st

from backend.orchestrator import BioSignalOrchestrator
from backend.coordination import acknowledge_action, assign_action, complete_action
from backend.public_sources import collect_singapore_public_data
from backend.reporting import decide_action
from backend.scenario_loader import available_scenarios, load_scenario
from backend.schemas import ActionStatus, TaskStatus


st.set_page_config(page_title="BIO-SIGNAL · GoonAI", page_icon="◉", layout="wide")

# --- Presentation helpers -------------------------------------------------
# Interactive controls stay native Streamlit widgets so behaviour and the
# automated tests are unchanged; only display elements use inline HTML.

STATUS_STYLE = {
    "investigate": ("investigate", "Investigation opened", "Confirm before any action"),
    "monitor": ("monitor", "Monitoring recommended", "No exceptional escalation"),
    "verify": ("verify", "Verification needed", "Reporting is uncertain or contradictory"),
}
HYPOTHESIS_CLASS = {
    "natural_zoonotic": "hyp-natural",
    "accidental_release": "hyp-accidental",
    "deliberate_release": "hyp-deliberate",
    "insufficient_evidence": "hyp-insufficient",
}
PIPELINE = [
    ("Ingest signals", "Normalise observations"),
    ("Correlate &amp; assess", "One Health + epidemiology"),
    ("Compare explanations", "Three origins + unresolved evidence"),
    ("Recommend &amp; approve", "Human verification gate"),
]


def esc(value: object) -> str:
    return html.escape(str(value))


def pretty(value: str) -> str:
    return value.replace("_", " ").title()


def pipeline_html() -> str:
    parts = []
    for position, (title, subtitle) in enumerate(PIPELINE, start=1):
        parts.append(
            f'<div class="pl-step"><div class="pl-num">{position}</div>'
            f'<div class="pl-text"><span class="pl-title">{title}</span>'
            f'<span class="pl-sub">{esc(subtitle)}</span></div></div>'
        )
        if position < len(PIPELINE):
            parts.append('<div class="pl-arrow">→</div>')
    return f'<div class="pipeline">{"".join(parts)}</div>'


def incoming_alert_html(scenario) -> str:
    """Present the selected synthetic inputs as one compact incoming alert."""

    rows = []
    for signal in scenario.initial_signals:
        domain = pretty(signal.domain.value)
        signal_name = pretty(signal.signal_type)
        rows.append(
            f'<div class="signal-row"><div class="signal-domain">{esc(domain)}</div>'
            f'<div class="signal-copy"><strong>{esc(signal_name)}</strong>'
            f'<span>{esc(signal.location_cell)} · {signal.timestamp:%d %b, %H:%M} UTC</span></div>'
            f'<div class="signal-value"><strong>{signal.observed_value:g}</strong>'
            f'<span>baseline {signal.baseline_mean:g} {esc(signal.unit)}</span></div></div>'
        )
    locations = {signal.location_cell for signal in scenario.initial_signals}
    location_summary = "same location" if len(locations) == 1 else f"{len(locations)} locations"
    return (
        '<section class="incoming" aria-label="Incoming simulated alert">'
        '<div class="incoming-head"><div><strong>Incoming simulated alert</strong>'
        f'<span>{len(rows)} unusual signals · {esc(location_summary)}</span></div>'
        '<div class="synthetic-label">Synthetic data</div></div>'
        f'<div class="signal-list">{"".join(rows)}</div></section>'
    )


def status_banner_html(profile) -> str:
    status_key = profile.status.value
    css_class, title, meaning = STATUS_STYLE.get(status_key, ("verify", "Assessment ready", ""))
    return (
        f'<section class="case-banner {css_class}" aria-label="Case assessment">'
        f'<div class="case-main"><div class="case-id">CASE {esc(profile.case_id)}</div>'
        f'<div class="case-title"><span class="case-dot"></span>{esc(title)}</div>'
        f'<div class="case-meaning">{esc(meaning)}</div>'
        f'</div>'
        f'<div class="case-facts"><div><span>Leading explanation</span>'
        f'<strong>{esc(pretty(profile.leading_hypothesis.value))}</strong></div>'
        f'<div><span>Heuristic confidence</span><strong>{esc(profile.confidence.value.title())}</strong></div></div>'
        f'</section>'
    )


def hypothesis_bars_html(assessments) -> str:
    rows = []
    for position, assessment in enumerate(assessments):
        name = assessment.hypothesis.value
        score = max(0, min(100, assessment.support_score))
        css_class = HYPOTHESIS_CLASS.get(name, "hyp-insufficient")
        leading = ' <span class="hyp-lead">leading</span>' if position == 0 else ""
        rows.append(
            f'<div class="hyp-row"><div class="hyp-head">'
            f'<span class="hyp-name">{esc(pretty(name))}{leading}</span>'
            f'<span class="hyp-val">{assessment.support_score}</span></div>'
            f'<div class="hyp-track"><div class="hyp-fill {css_class}" style="width:{score}%"></div></div>'
            f'</div>'
        )
    return f'<div class="hyp-list">{"".join(rows)}</div>'


def trace_timeline_html(records) -> str:
    steps = []
    for record in records:
        role = pretty(record.responsible_role or "controller")
        ok_class = "step-ok" if record.success else "step-fail"
        ok_mark = "✓" if record.success else "✗"
        steps.append(
            f'<div class="tl-step"><div class="tl-num">{record.sequence}</div>'
            f'<div class="tl-body"><div class="tl-head">'
            f'<code class="tl-tool">{esc(record.tool_name)}</code>'
            f'<span class="role-badge">{esc(role)}</span>'
            f'<span class="{ok_class}">{ok_mark}</span>'
            f'<span class="tl-lat">{record.latency_ms} ms</span></div>'
            f'<div class="tl-sum">{esc(record.summary)}</div></div></div>'
        )
    return f'<div class="timeline">{"".join(steps)}</div>'


def render_action(profile, action) -> None:
    """Render one human decision without dispatching the proposed action."""

    st.markdown(f"**{action.title}**")
    st.caption(f"Owner: {action.owner} · Consequence: {action.consequence}")
    st.write(action.rationale)
    st.caption(f"Evidence: {', '.join(action.evidence_ids) or 'No evidence linked'}")
    if action.completion_criterion:
        st.write(f"Completion: {action.completion_criterion}")
    if action.depends_on:
        st.caption(f"Prerequisites: {', '.join(action.depends_on)}")
    key = f"{profile.case_id}-{profile.revision}-{action.action_id}"
    actor = st.text_input("Reviewer / task recorder (self-reported)", value="Local demo reviewer", key=f"actor-{key}")
    pending = action.status == ActionStatus.PENDING
    approve_col, reject_col = st.columns(2)
    approve = approve_col.button("Approve", key=f"approve-{key}", disabled=not pending or not actor.strip(), use_container_width=True)
    reject = reject_col.button("Reject", key=f"reject-{key}", disabled=not pending or not actor.strip(), use_container_width=True)
    if approve or reject:
        decide_action(profile, action.action_id, approve, actor=actor)
        st.session_state.profile = profile
        st.rerun()
    st.caption(f"Decision: {action.status.value} · Task: {action.task_status.value}")
    if action.due_at:
        overdue = action.due_at < datetime.now(timezone.utc) and action.task_status != TaskStatus.COMPLETED
        st.caption(f"Deadline: {action.due_at:%Y-%m-%d %H:%M %Z}" + (" · Overdue" if overdue else ""))
    if action.result:
        st.write(f"Recorded result: {action.result}")
    if action.status != ActionStatus.APPROVED:
        return
    try:
        if action.task_status == TaskStatus.UNASSIGNED:
            actions = {item.action_id: item for item in profile.proposed_actions}
            blocked = any(dependency not in actions or actions[dependency].task_status != TaskStatus.COMPLETED
                          for dependency in action.depends_on)
            if blocked:
                st.info("Complete the prerequisite tasks before assigning this follow-on review.")
            hours = st.number_input("Deadline in hours from assignment", min_value=1, max_value=720, value=24, key=f"deadline-{key}")
            if st.button("Assign locally", key=f"assign-{key}", disabled=blocked or not actor.strip()):
                assign_action(profile, action.action_id, actor=actor, due_at=datetime.now(timezone.utc) + timedelta(hours=hours))
                st.rerun()
        elif action.task_status == TaskStatus.ASSIGNED:
            if st.button("Record acknowledgement", key=f"ack-{key}", disabled=not actor.strip()):
                acknowledge_action(profile, action.action_id, actor=actor)
                st.rerun()
        elif action.task_status == TaskStatus.ACKNOWLEDGED:
            result = st.text_area("Verification result (synthetic or public only)", key=f"result-{key}",
                                  help="Include provenance, reporting time and unavailable or inconclusive outcomes. Text is retained locally and does not change hypothesis scores.")
            if st.button("Record completion", key=f"complete-{key}", disabled=not result.strip() or not actor.strip()):
                complete_action(profile, action.action_id, actor=actor, result=result)
                st.rerun()
    except ValueError as exc:
        st.error(str(exc))


st.markdown(
    """
    <style>
      :root {
        --surface: #fbfaf6; --surface-2: #f0ece1; --border: #e2ddce;
        --ink: #22231f; --ink-2: #4c5249; --muted: #7c8175;
        --green: #3f7a5c; --green-deep: #2f5c45;
        --investigate-fg: #8a5e10; --investigate-bg: #f6e7c3; --investigate-bd: #e2c479;
        --monitor-fg: #266a4c; --monitor-bg: #d9ebdf; --monitor-bd: #a9d2ba;
        --verify-fg: #245f8f; --verify-bg: #d7e6f2; --verify-bd: #a8c8e4;
      }
      header[data-testid="stHeader"] { height:0; background:transparent; }
      [data-testid="stToolbar"], footer { display:none; }
      .block-container { max-width: 1180px; padding-top:1.35rem; padding-bottom:2rem; }
      h1, h2, h3 { letter-spacing: -0.02em; color: var(--ink); }
      .stApp h2 { font-size:1.25rem; margin-top:.2rem; }
      .stCaption { color:var(--muted); }

      .hero { display:flex; align-items:center; gap:.65rem; margin-bottom:.1rem; }
      .hero-mark { width:26px; height:26px; border:2px solid var(--green); border-radius:50%;
        background:var(--surface); position:relative; flex:0 0 auto; }
      .hero-mark::after { content:""; width:8px; height:8px; border-radius:50%;
        background:var(--green); position:absolute; inset:7px; }
      .hero-word { font-size:1.65rem; font-weight:760; letter-spacing:.015em; color:var(--ink); line-height:1.1; }
      .hero-tag { color:var(--ink-2); font-size:.9rem; margin:0 0 .75rem 0; }

      .pipeline { display:flex; align-items:stretch; gap:.4rem; flex-wrap:wrap;
        border-top:1px solid var(--border); border-bottom:1px solid var(--border);
        padding:.55rem 0; margin-bottom:.7rem; }
      .pl-step { display:flex; align-items:center; gap:.55rem; flex:1 1 150px; min-width:140px; }
      .pl-num { width:22px; height:22px; border-radius:50%; background:var(--green);
        color:#fff; font-size:.8rem; font-weight:700; display:flex; align-items:center;
        justify-content:center; flex:0 0 auto; }
      .pl-text { display:flex; flex-direction:column; line-height:1.2; min-width:0; }
      .pl-title { font-weight:650; font-size:.82rem; color:var(--ink); white-space:nowrap; }
      .pl-sub { font-size:.7rem; color:var(--muted); white-space:nowrap; }
      .pl-arrow { color:var(--border); font-size:1.1rem; display:flex; align-items:center; flex:0 0 auto; }

      .incoming { border:1px solid var(--border); border-radius:10px; overflow:hidden;
        background:var(--surface); margin:.25rem 0 .65rem; }
      .incoming-head { display:flex; justify-content:space-between; align-items:center;
        gap:1rem; padding:.65rem .85rem; border-bottom:1px solid var(--border); }
      .incoming-head > div:first-child { display:flex; align-items:baseline; gap:.55rem; }
      .incoming-head strong { color:var(--ink); font-size:.9rem; }
      .incoming-head span { color:var(--muted); font-size:.78rem; }
      .synthetic-label { color:var(--green-deep); font-size:.75rem; font-weight:650; }
      .signal-list { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); }
      .signal-row { display:grid; grid-template-columns:4.5rem 1fr auto; align-items:center;
        gap:.65rem; min-width:0; padding:.7rem .85rem; }
      .signal-row + .signal-row { border-left:1px solid var(--border); }
      .signal-domain { color:var(--green-deep); font-size:.78rem; font-weight:700; }
      .signal-copy, .signal-value { display:flex; flex-direction:column; min-width:0; }
      .signal-copy strong { color:var(--ink); font-size:.82rem; overflow:hidden;
        text-overflow:ellipsis; white-space:nowrap; }
      .signal-copy span, .signal-value span { color:var(--muted); font-size:.7rem; white-space:nowrap; }
      .signal-value { text-align:right; }
      .signal-value strong { color:var(--ink); font-size:1rem; font-variant-numeric:tabular-nums; }

      .case-banner { display:flex; justify-content:space-between; align-items:center; gap:1rem;
        border-radius:10px; padding:.85rem 1rem; border:1px solid; margin:.2rem 0 .35rem; }
      .case-banner.investigate { background:var(--investigate-bg); border-color:var(--investigate-bd); }
      .case-banner.monitor { background:var(--monitor-bg); border-color:var(--monitor-bd); }
      .case-banner.verify { background:var(--verify-bg); border-color:var(--verify-bd); }
      .case-id { color:var(--ink-2); font-size:.7rem; font-weight:650; }
      .case-title { display:flex; align-items:center; gap:.5rem; color:var(--ink);
        font-size:1.35rem; font-weight:760; letter-spacing:-.02em; line-height:1.25; }
      .case-dot { width:9px; height:9px; border-radius:50%; background:currentColor; }
      .investigate .case-dot { color:var(--investigate-fg); }
      .monitor .case-dot { color:var(--monitor-fg); }
      .verify .case-dot { color:var(--verify-fg); }
      .case-meaning { color:var(--ink-2); font-size:.8rem; }
      .case-facts { display:flex; align-items:stretch; }
      .case-facts > div { min-width:140px; padding:.1rem .9rem; border-left:1px solid rgba(34,35,31,.16); }
      .case-facts span, .case-facts strong { display:block; }
      .case-facts span { color:var(--ink-2); font-size:.7rem; }
      .case-facts strong { color:var(--ink); font-size:.9rem; margin-top:.1rem; }

      .hyp-list { display:flex; flex-direction:column; gap:.7rem; }
      .hyp-head { display:flex; justify-content:space-between; align-items:baseline;
        font-size:.9rem; margin-bottom:.25rem; }
      .hyp-name { color:var(--ink); font-weight:600; }
      .hyp-lead { font-size:.68rem; text-transform:uppercase; letter-spacing:.06em;
        color:var(--green-deep); margin-left:.3rem; }
      .hyp-val { color:var(--ink-2); font-variant-numeric:tabular-nums; font-weight:650; }
      .hyp-track { height:8px; background:var(--surface-2); border-radius:3px; overflow:hidden; }
      .hyp-fill { height:100%; border-radius:3px; }
      .hyp-natural { background:#3f8f6b; }
      .hyp-accidental { background:#c8901f; }
      .hyp-deliberate { background:#b5502f; }
      .hyp-insufficient { background:#8a8f83; }
      .reasoning-note { margin-top:.85rem; padding:.65rem .75rem; background:var(--surface);
        border:1px solid var(--border); border-radius:8px; color:var(--ink-2);
        font-size:.82rem; line-height:1.4; }
      .reasoning-note strong { display:block; color:var(--green-deep); margin-bottom:.15rem; }

      .timeline { display:flex; flex-direction:column; }
      .tl-step { display:flex; gap:.7rem; padding-bottom:.65rem; position:relative; }
      .tl-step:not(:last-child)::before { content:""; position:absolute; left:13px; top:28px;
        bottom:0; width:2px; background:var(--border); }
      .tl-num { width:28px; height:28px; border-radius:50%; background:var(--green-deep);
        color:#fff; font-weight:700; font-size:.85rem; display:flex; align-items:center;
        justify-content:center; flex:0 0 auto; z-index:1; }
      .tl-body { background:var(--surface); border:1px solid var(--border); border-radius:10px;
        padding:.55rem .8rem; flex:1 1 auto; }
      .tl-head { display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; }
      .tl-tool { background:var(--surface-2); border-radius:5px; padding:.1rem .4rem;
        font-size:.82rem; color:var(--green-deep); }
      .role-badge { font-size:.72rem; text-transform:uppercase; letter-spacing:.04em;
        color:var(--green-deep); background:#e4efe8; border:1px solid var(--monitor-bd);
        border-radius:5px; padding:.08rem .4rem; }
      .step-ok { color:var(--monitor-fg); font-weight:700; }
      .step-fail { color:var(--investigate-fg); font-weight:700; }
      .tl-lat { color:var(--muted); font-size:.76rem; margin-left:auto; }
      .tl-sum { color:var(--ink-2); font-size:.86rem; margin-top:.3rem; line-height:1.4; }

      .stButton > button { border-radius:8px; min-height:2.4rem; }
      .stAlert { border-radius:8px; }
      details { border-radius:8px !important; }
      div[data-testid="stVerticalBlockBorderWrapper"] { border-color:var(--border); border-radius:10px; }
      .demo-meta { color:var(--muted); font-size:.76rem; margin:.1rem 0 .45rem; }

      @media (max-width: 800px) {
        .block-container { padding-top:.8rem; }
        .pl-arrow, .pl-sub { display:none; }
        .pipeline { gap:.7rem; }
        .pl-step { flex-basis:45%; }
        .signal-list { grid-template-columns:1fr; }
        .signal-row + .signal-row { border-left:0; border-top:1px solid var(--border); }
        .case-banner { align-items:flex-start; flex-direction:column; }
        .case-facts { width:100%; }
        .case-facts > div:first-child { border-left:0; padding-left:0; }
      }
      @media (prefers-reduced-motion: reduce) { * { transition:none !important; } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="hero"><div class="hero-mark"></div>'
    '<div class="hero-word">BIO-SIGNAL</div></div>'
    '<p class="hero-tag">Agentic biological-risk triage for Singapore — connects fragmented '
    'signals and recommends what a human should verify next. By GoonAI.</p>',
    unsafe_allow_html=True,
)
st.markdown(pipeline_html(), unsafe_allow_html=True)

scenario_names = available_scenarios()
if "zoonotic_spillover" in scenario_names:
    scenario_names.remove("zoonotic_spillover")
    scenario_names.insert(0, "zoonotic_spillover")

setup_expanded = st.session_state.get("profile") is None
setup_label = "Demo setup" if setup_expanded else "Demo setup · case created"
with st.expander(setup_label, expanded=setup_expanded):
    source_mode = st.radio(
        "Input source",
        ["Singapore public data", "Curated scenario"],
        index=1,
        horizontal=True,
        help="Public mode retrieves current official aggregate sources. Curated scenarios exercise behaviours that public feeds cannot expose.",
    )
    control_left, control_middle = st.columns([3, 1])
    with control_left:
        selected = st.selectbox(
            "Scenario",
            scenario_names,
            format_func=lambda value: load_scenario(value).title,
            disabled=source_mode == "Singapore public data",
        )
    with control_middle:
        mode = st.selectbox("Decision mode", ["replay", "live"], help="Live uses Sonnet 5 on Bedrock.")
    scenario = load_scenario(selected)
    if source_mode == "Curated scenario":
        st.markdown(incoming_alert_html(scenario), unsafe_allow_html=True)
        st.caption(scenario.data_notice)
    else:
        st.info(
            "Retrieves only allow-listed, public aggregate sources. No patient records or private agency feeds are used.",
            icon="ℹ️",
        )
    start_row, start_action = st.columns([3, 1])
    with start_row:
        st.caption("Replay mode is deterministic and requires no AWS credentials.")
    with start_action:
        start = st.button("Start investigation", type="primary", use_container_width=True)

if start:
    # Commit the matching profile and snapshot together only after a successful run.
    try:
        with st.spinner("Collecting sources and running the bounded investigation…"):
            orchestrator = BioSignalOrchestrator(mode=mode)
            if source_mode == "Singapore public data":
                bundle = collect_singapore_public_data()
                profile = orchestrator.run_public(bundle)
            else:
                profile = orchestrator.run(scenario)
                bundle = None
            st.session_state.profile = profile
            st.session_state.public_bundle = bundle
            st.session_state.evidence_injected = False
            st.session_state.profile_source = source_mode
            st.session_state.profile_scenario = selected if source_mode == "Curated scenario" else None
            st.session_state.profile_mode = mode
            st.rerun()
    except Exception as exc:
        st.error(f"Investigation failed safely: {exc}")
        st.stop()

profile = st.session_state.get("profile")
if (
    profile is None
    or st.session_state.get("profile_source") != source_mode
    or (
        source_mode == "Curated scenario"
        and st.session_state.get("profile_scenario") != selected
    )
    or st.session_state.get("profile_mode") != mode
):
    if source_mode == "Singapore public data":
        st.caption(
            "Ready to assemble current public Singapore health, environment, food, travel and "
            "WHO outbreak signals into one evidence-linked risk profile."
        )
    else:
        st.caption(f"Ready · {scenario.description}")
    st.stop()

st.markdown(status_banner_html(profile), unsafe_allow_html=True)
st.markdown(
    f'<div class="demo-meta">Generated {profile.generated_at:%Y-%m-%d %H:%M %Z} · '
    f'{profile.metrics.tool_calls} bounded tool calls · {profile.metrics.model_calls} model calls · '
    f'estimated model cost US${profile.metrics.estimated_cost_usd:.4f}</div>',
    unsafe_allow_html=True,
)
if profile.metrics.fallback_used:
    st.warning("The live controller was unavailable or reached its call limit. Replay completed this assessment.")

if source_mode == "Curated scenario" and scenario.new_evidence_signals:
    update_copy, update_action = st.columns([3, 1])
    with update_copy:
        if st.session_state.get("evidence_injected", False):
            st.success("New evidence added. The previous assessment and decisions remain in the case history.")
        else:
            st.markdown("**New evidence is available**")
            st.caption(f"{len(scenario.new_evidence_signals)} supplied synthetic observation(s) can be added to this case.")
    inject_evidence = update_action.button(
        "Inject new synthetic evidence",
        type="primary",
        disabled=st.session_state.get("evidence_injected", False),
        use_container_width=True,
    )
    if inject_evidence:
        try:
            with st.spinner("Re-assessing with the evidence packet…"):
                updated = BioSignalOrchestrator(mode=mode).reassess(scenario, profile)
            st.session_state.profile = updated
            st.session_state.evidence_injected = True
            st.rerun()
        except Exception as exc:
            st.error(f"Evidence injection failed safely: {exc}")

if st.session_state.get("evidence_injected", False) and profile.change_log:
    st.info(f"Assessment update · {profile.change_log[-1]}")

if profile.source_coverage:
    with st.expander(f"Public-source coverage · {len(profile.source_coverage)} sources"):
        st.caption("Unavailable measurements remain visible as evidence gaps; they are never imputed by the model.")
        coverage_header = (
            "| Domain | Publisher / source | Status | Observations | Cadence |\n"
            "| --- | --- | --- | ---: | --- |"
        )
        coverage_lines = [
            f"| {source.domain.value} | [{source.title}]({source.url}) | {source.status.value} | "
            f"{source.observation_count} | {source.cadence} |"
            for source in profile.source_coverage
        ]
        st.markdown("\n".join([coverage_header, *coverage_lines]))
        for source in profile.source_coverage:
            st.write(f"{source.source_id} — {source.status.value}: {source.note}")
            st.caption(f"Retrieved: {source.retrieved_at:%Y-%m-%d %H:%M %Z}")

    public_bundle = st.session_state.get("public_bundle")
    if public_bundle is not None:
        st.download_button(
            "Download normalised public-data snapshot",
            public_bundle.model_dump_json(indent=2),
            file_name=f"singapore-public-data-{public_bundle.retrieved_at:%Y%m%dT%H%M}.json",
            mime="application/json",
        )

assessment_col, verification_col = st.columns([3, 2], gap="large")
with assessment_col:
    st.header("Compare explanations")
    st.caption("Relative evidence support, not scientific probability")
    st.markdown(hypothesis_bars_html(profile.hypotheses), unsafe_allow_html=True)

    connected_finding = next(
        (item.finding for item in profile.known_findings if item.evidence_id.startswith("EV-CORR")),
        None,
    )
    if connected_finding:
        st.markdown(
            f'<div class="reasoning-note"><strong>Why the signals connect</strong>'
            f'{esc(connected_finding)}</div>',
            unsafe_allow_html=True,
        )

with verification_col:
    st.header("Recommended next check")
    st.caption("The primary check is shown first; supporting checks and joint review follow below.")
    st.caption("The system proposes; a person decides. No action is dispatched automatically.")
    st.caption("Coordination is a local simulation. Reviewer labels are self-reported; no agency receives these tasks.")

    if profile.proposed_actions:
        with st.container(border=True):
            render_action(profile, profile.proposed_actions[0])
    if len(profile.proposed_actions) > 1:
        with st.expander("Supporting checks and joint review"):
            for action in profile.proposed_actions[1:]:
                render_action(profile, action)

with st.expander("Executive brief and impact"):
    st.write(profile.executive_brief)
    st.write(profile.impact.summary)
    st.caption(f"Input sensitivity: {profile.sensitivity} · Severity: {profile.impact.severity}")
    st.caption("Anomalous domains: " + (", ".join(domain.value for domain in profile.impact.affected_domains) or "unassessed"))

with st.expander(f"Specialist functions · {len(profile.agent_functions)}"):
    st.caption("One controller invokes deterministic specialist tools. The functions share evidence; agreement between them is not independent corroboration.")
    for function in profile.agent_functions:
        st.markdown(f"**{function.name}** · {pretty(function.status)}")
        st.write(function.summary)

with st.expander(f"Event graph · {len(profile.event_graph.nodes)} signals, {len(profile.event_graph.links)} links"):
    st.caption(profile.event_graph.limitations)
    if profile.event_graph.nodes:
        st.dataframe([node.model_dump(mode="json") for node in profile.event_graph.nodes], hide_index=True, width="stretch")
    if profile.event_graph.links:
        st.dataframe([{"From": link.signal_ids[0], "To": link.signal_ids[1], "Hours apart": link.gap_hours,
                       "Relationship": pretty(link.relationship)} for link in profile.event_graph.links],
                     hide_index=True, width="stretch")

with st.expander(f"Case history · revision {profile.revision}"):
    st.caption(f"Assessment runtime: {profile.metrics.assessment_duration_ms} ms. This excludes source collection and human review time.")
    for change in profile.change_log:
        st.write(change)
    for revision in [*profile.previous_assessments, profile]:
        st.markdown(f"**Revision {revision.revision}** · {revision.generated_at:%Y-%m-%d %H:%M %Z}")
        st.caption(f"{len(revision.known_findings)} findings · {pretty(revision.leading_hypothesis.value)} · {revision.confidence.value} confidence")
        for event in revision.action_history:
            st.write(f"{event.recorded_at:%Y-%m-%d %H:%M %Z} · {event.actor} · {event.action_id} · {event.event}: {event.note}")

evidence_col, uncertainty_col = st.columns(2, gap="large")
with evidence_col:
    with st.expander(f"Evidence ledger · {len(profile.known_findings)} findings"):
        for evidence in profile.known_findings:
            st.markdown(f"**{evidence.evidence_id}** — {evidence.finding}")
            st.caption(
                f"Quality {evidence.quality:.0%} · Sources: "
                + (", ".join(evidence.source_ids) or "none supplied")
            )
            st.caption(f"Limitation: {evidence.limitations}")

with uncertainty_col:
    with st.expander(f"Uncertainty · {len(profile.uncertainty)} open questions"):
        for question in profile.uncertainty:
            st.write(f"• {question}")

with st.expander(f"Agent trace · {len(profile.tool_trace)} bounded steps"):
    st.caption("Each step is one bounded tool call, tagged with the specialist role responsible for it.")
    st.markdown(trace_timeline_html(profile.tool_trace), unsafe_allow_html=True)

st.download_button(
    "Download risk profile JSON",
    profile.model_dump_json(indent=2),
    file_name=f"{profile.case_id}.json",
    mime="application/json",
)
