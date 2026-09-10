"""The eight BIO-SIGNAL functions, implemented by tools around one controller.

These describe executed deterministic functions and explicit unavailable work;
they do not represent eight independent model opinions or background workers.
"""

from .schemas import AgentFunction, CaseState


AGENT_FUNCTIONS = {
    "sentinel": ("Sentinel", ["anomaly_evidence", "public_bundle_to_evidence"]),
    "correlation": ("Correlation", ["correlate_signals", "build_event_graph"]),
    "epidemiology": ("Epidemiology", ["assess_spread_plausibility"]),
    "threat_assessment": ("Threat Assessment", ["score_hypotheses", "estimate_confidence"]),
    "external_intel": ("OSINT / External Intel", ["verify_external_report", "public_bundle_to_evidence"]),
    "verification": ("Verification", ["recommend_next_check"]),
    "coordination": ("Coordination", ["coordinate_verification", "assign_action", "acknowledge_action", "complete_action"]),
    "briefing": ("Briefing", ["build_risk_profile", "generate_brief"]),
}


def describe_agent_functions(state: CaseState) -> list[AgentFunction]:
    """Summarise actual coverage after investigation, scoring and briefing."""

    has_external = any(item.evidence_id.startswith(("EV-REPORT-", "EV-PUBLIC-WHO")) for item in state.evidence)
    descriptions = {
        "sentinel": ("completed", "Screened the supplied snapshot against available baselines; collection is on demand."),
        "correlation": (
            "unavailable" if state.is_public else "completed",
            "Public aggregates lack comparable locations and event times." if state.is_public else
            f"Built {len(state.event_graph.nodes)} event nodes and {len(state.event_graph.links)} cross-domain links; scored human/animal pairs only.",
        ),
        "epidemiology": (
            "unavailable" if state.is_public else "completed",
            "Comparable signal-level times are unavailable." if state.is_public else
            "Checked animal/human temporal fit. Growth estimation and validated epidemiological modelling remain unavailable.",
        ),
        "threat_assessment": ("completed", "Compared natural zoonotic, accidental, deliberate and insufficient-evidence support; confidence is uncalibrated."),
        "external_intel": (
            "completed" if has_external else "unavailable",
            "Reviewed supplied external claims or official public context with provenance." if has_external else
            "No external evidence supplied; no partner, HUMINT or SIGINT integration is configured.",
        ),
        "verification": ("completed", "Selected one primary check from approved candidates using a qualitative uncertainty heuristic."),
        "coordination": ("awaiting_human", "Prepared scoped proposals and dependencies; local assignment requires human approval and a deadline."),
        "briefing": ("completed", "Produced an evidence-linked risk profile, impact limitations and executive brief."),
    }
    return [AgentFunction(role_id=role_id, name=name, tools=tools,
                          status=descriptions[role_id][0], summary=descriptions[role_id][1])
            for role_id, (name, tools) in AGENT_FUNCTIONS.items()]
