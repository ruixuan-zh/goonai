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
      .stApp { background: #f4f1e9; color: #22231f; }
      [data-testid="stHeader"] { background: #f4f1e9; }
      h1, h2, h3 { color: #1f2923; letter-spacing: -0.02em; }
      .block-container { max-width: 1160px; padding-top: 2.2rem; }
      div[data-testid="stMetric"] { border-top: 2px solid #53685a; padding-top: .7rem; }
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
    try:
        with st.spinner("Collecting sources and running the bounded investigation…"):
            orchestrator = BioSignalOrchestrator(mode=mode)
            if source_mode == "Singapore public data":
                bundle = collect_singapore_public_data()
                st.session_state.public_bundle = bundle
                st.session_state.profile = orchestrator.run_public(bundle)
            else:
                st.session_state.profile = orchestrator.run(scenario)
                st.session_state.public_bundle = None
            st.session_state.profile_source = source_mode
            st.session_state.profile_scenario = selected if source_mode == "Curated scenario" else None
            st.session_state.profile_mode = mode
    except Exception as exc:
        st.error(f"Investigation failed safely: {exc}")

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
    st.subheader("Ready to investigate")
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

if source_mode == "Curated scenario" and scenario.new_evidence_signals:
    if st.button("Inject new synthetic evidence"):
        previous_leader = profile.leading_hypothesis.value
        previous_confidence = profile.confidence.value
        try:
            with st.spinner("Re-assessing with the evidence packet…"):
                updated = BioSignalOrchestrator(mode=mode).run(scenario, include_new_evidence=True)
            updated.change_log.append(
                f"Leading hypothesis: {previous_leader} → {updated.leading_hypothesis.value}; "
                f"confidence: {previous_confidence} → {updated.confidence.value}."
            )
            st.session_state.profile = updated
            st.rerun()
        except Exception as exc:
            st.error(f"Evidence injection failed safely: {exc}")

if profile.source_coverage:
    st.subheader("Public-source coverage")
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
    st.subheader("Hypothesis support")
    st.caption("Relative evidence support, not scientific probability")
    for assessment in profile.hypotheses:
        label = assessment.hypothesis.value.replace("_", " ").title()
        st.write(f"{label} — {assessment.support_score}/100")
        st.progress(assessment.support_score)

    st.subheader("Known findings")
    for evidence in profile.known_findings:
        with st.expander(f"{evidence.evidence_id} · quality {evidence.quality:.0%}"):
            st.write(evidence.finding)
            st.caption(f"Limitation: {evidence.limitations}")
            st.caption("Sources: " + (", ".join(evidence.source_ids) or "none supplied"))

with right:
    st.subheader("Uncertainty")
    for question in profile.uncertainty:
        st.write(f"• {question}")

    st.subheader("Recommended verification")
    for check in profile.recommended_verification:
        st.write(f"• {check}")

    st.subheader("Human approval gate")
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

st.subheader("Agent trace")
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
    st.subheader("What changed")
    for change in profile.change_log:
        st.write(f"• {change}")

st.download_button(
    "Download risk profile JSON",
    profile.model_dump_json(indent=2),
    file_name=f"{profile.case_id}.json",
    mime="application/json",
)
