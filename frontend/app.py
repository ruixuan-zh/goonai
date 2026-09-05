"""A restrained Streamlit interface for the BIO-SIGNAL demonstration."""

from __future__ import annotations

import sys
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
from backend.public_sources import collect_singapore_public_data
from backend.reporting import decide_action
from backend.scenario_loader import available_scenarios, load_scenario


st.set_page_config(page_title="BIO-SIGNAL", page_icon="◉", layout="wide")
st.markdown(
    """
    <style>
      h1, h2, h3 { letter-spacing: -0.02em; }
      .stApp h2 { font-size: 1.75rem; }
      .block-container { max-width: 1160px; padding-top: 2.2rem; }
      div[data-testid="stMetric"] { border-top: 2px solid #53685a; padding-top: .7rem; }
      .stApp [data-testid="stMetricValue"] p { white-space: normal; overflow-wrap: anywhere; }
      .stButton > button { border-radius: 3px; border: 1px solid #445548; }
      .stAlert { border-radius: 3px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("BIO-SIGNAL")
st.caption("Singapore biological-risk differential · public aggregates or curated scenarios")

scenario_names = available_scenarios()
if "zoonotic_spillover" in scenario_names:
    scenario_names.remove("zoonotic_spillover")
    scenario_names.insert(0, "zoonotic_spillover")
source_mode = st.radio(
    "Input source",
    ["Singapore public data", "Curated scenario"],
    horizontal=True,
    help="Public mode retrieves current official aggregate sources. Curated scenarios exercise behaviours that public feeds cannot expose.",
)
control_left, control_middle, control_right = st.columns([2, 1, 1])
with control_left:
    selected = st.selectbox(
        "Scenario",
        scenario_names,
        format_func=lambda value: load_scenario(value).title,
        disabled=source_mode == "Singapore public data",
    )
with control_middle:
    mode = st.selectbox("Decision mode", ["replay", "live"], help="Live uses Sonnet 5 on Bedrock.")
with control_right:
    st.write("")
    start = st.button("Start investigation", type="primary", use_container_width=True)

scenario = load_scenario(selected)
if source_mode == "Singapore public data":
    st.info(
        "Retrieves only allow-listed, public aggregate sources. No patient records or private agency feeds are used.",
        icon="ℹ️",
    )
else:
    st.info(scenario.data_notice, icon="ℹ️")

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
    st.header("Ready to investigate")
    if source_mode == "Singapore public data":
        st.write(
            "Collect the latest CDA, NEA, data.gov.sg, SFA, AVS, wastewater-programme and "
            "Changi public information plus WHO outbreak intelligence, then build an "
            "evidence-linked Singapore risk profile."
        )
    else:
        st.write(scenario.description)
    st.write(
        "The replay path requires no AWS credentials. Select live mode only after configuring "
        "Bedrock access in your local `.env` or AWS profile."
    )
    st.stop()

status_col, hypothesis_col, confidence_col, cost_col = st.columns(4)
status_col.metric("Case status", profile.status.value.upper())
hypothesis_col.metric("Leading hypothesis", profile.leading_hypothesis.value.replace("_", " ").title())
confidence_col.metric("Confidence", profile.confidence.value.upper())
cost_col.metric("Estimated model cost", f"US${profile.metrics.estimated_cost_usd:.4f}")
st.caption(f"Assessment generated: {profile.generated_at:%Y-%m-%d %H:%M %Z}")
if profile.metrics.fallback_used:
    st.warning("The live controller was unavailable or reached its call limit. Replay completed this assessment.")

if source_mode == "Curated scenario" and scenario.new_evidence_signals:
    if st.button("Inject new synthetic evidence", disabled=st.session_state.get("evidence_injected", False)):
        previous_leader = profile.leading_hypothesis.value
        previous_confidence = profile.confidence.value
        previous_scores = {
            assessment.hypothesis: assessment.support_score for assessment in profile.hypotheses
        }
        try:
            with st.spinner("Re-assessing with the evidence packet…"):
                updated = BioSignalOrchestrator(mode=mode).run(scenario, include_new_evidence=True)
            score_changes = []
            for assessment in updated.hypotheses:
                change = assessment.support_score - previous_scores.get(assessment.hypothesis, 0)
                if change:
                    label = assessment.hypothesis.value.replace("_", " ").title()
                    score_changes.append(f"{label} {change:+d}")
            score_summary = ", ".join(score_changes) or "no support-score movement"
            updated.change_log.append(
                f"Leading hypothesis: {previous_leader} → {updated.leading_hypothesis.value}; "
                f"confidence: {previous_confidence} → {updated.confidence.value}; "
                f"support shifts: {score_summary}."
            )
            st.session_state.profile = updated
            st.session_state.evidence_injected = True
            st.rerun()
        except Exception as exc:
            st.error(f"Evidence injection failed safely: {exc}")

if profile.source_coverage:
    st.header("Public-source coverage")
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
    with st.expander("Source retrieval details and limitations"):
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

left, right = st.columns([3, 2], gap="large")
with left:
    st.header("Hypothesis support")
    st.caption("Relative evidence support, not scientific probability")
    for assessment in profile.hypotheses:
        label = assessment.hypothesis.value.replace("_", " ").title()
        st.progress(assessment.support_score, text=f"{label} — {assessment.support_score}/100")

    st.header("Known findings")
    for evidence in profile.known_findings:
        with st.expander(f"{evidence.evidence_id} · quality {evidence.quality:.0%}"):
            st.write(evidence.finding)
            st.caption(f"Limitation: {evidence.limitations}")
            st.caption("Sources: " + (", ".join(evidence.source_ids) or "none supplied"))

with right:
    st.header("Uncertainty")
    for question in profile.uncertainty:
        st.write(f"• {question}")

    st.header("Recommended verification")
    for check in profile.recommended_verification:
        st.write(f"• {check}")

    st.header("Human approval gate")
    for action in profile.proposed_actions:
        st.write(action.title)
        st.caption(f"Owner: {action.owner} · Consequence: {action.consequence}")
        st.write(action.rationale)
        approve_col, reject_col = st.columns(2)
        if approve_col.button("Approve", key=f"approve-{action.action_id}", use_container_width=True):
            decide_action(profile, action.action_id, True)
            st.session_state.profile = profile
            st.rerun()
        if reject_col.button("Reject", key=f"reject-{action.action_id}", use_container_width=True):
            decide_action(profile, action.action_id, False)
            st.session_state.profile = profile
            st.rerun()
        st.caption(f"Decision: {action.status.value}")

st.header("Agent trace")
# Rendered as Markdown rather than st.dataframe/st.table so the demo has no
# dependency on pyarrow, whose native library is fragile on some platforms.
trace_header = (
    "| Step | Tool | Result | Success | Controller |\n"
    "| --- | --- | --- | --- | --- |"
)
trace_lines = [
    f"| {record.sequence} | `{record.tool_name}` | {record.summary} | "
    f"{'✓' if record.success else '✗'} | {record.model_id} |"
    for record in profile.tool_trace
]
st.markdown("\n".join([trace_header, *trace_lines]))

if profile.change_log:
    st.header("What changed")
    for change in profile.change_log:
        st.write(f"• {change}")

st.download_button(
    "Download risk profile JSON",
    profile.model_dump_json(indent=2),
    file_name=f"{profile.case_id}.json",
    mime="application/json",
)
