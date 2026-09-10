"""Functional reviews and simulated task routing informed by incident coordination.

These are deterministic specialists sharing one evidence ledger. Agency labels
are illustrative Singapore routing suggestions, not operational integrations.
"""

from __future__ import annotations

from .schemas import CaseState, Domain, ProposedAction, SourceStatus, SpecialistReview


ROLE_DOMAINS = {
    "clinical_surveillance": (Domain.HUMAN,),
    "one_health": (Domain.ANIMAL, Domain.ENVIRONMENTAL, Domain.FOOD),
    "external_verification": (Domain.EXTERNAL, Domain.MOBILITY),
}
RESPONSIBILITIES = {
    "clinical_surveillance": "Review clinical signals and request epidemiological confirmation; do not infer a pathogen from symptoms.",
    "one_health": "Review animal, environmental and food coverage; distinguish missing measurements from negative findings.",
    "external_verification": "Preserve external claims and behavioural context; corroboration does not establish origin or intent.",
    "data_quality": "Review event and reporting times, provenance and dependence before interpreting evidence.",
    "epidemiology": "Check temporal and geographical consistency; association is not transmission or a calibrated forecast.",
    "assessment": "Compare competing explanations and preserve unresolved attribution without counting role agreement as evidence.",
}
TOOL_ROLES = {
    "correlate_signals": "correlation",
    "assess_spread_plausibility": "epidemiology",
    "verify_external_report": "external_intel",
    "recommend_next_check": "verification",
    "finish_investigation": "briefing",
}
TASK_OWNERS = {
    "corroborate-external-report": "Authorised external-information liaison",
    "obtain-critical-surveillance": "One Health liaison: NParks/AVS and NEA/PUB, with CDA",
    "paired-laboratory-confirmation": "CDA and NParks/AVS laboratory liaison",
    "clinical-cluster-review": "CDA clinical surveillance duty officer",
    "reconcile-reporting-delay": "Source data steward and surveillance analyst",
    "repeat-surveillance-review": "CDA surveillance analyst with One Health partners",
}


def review_specialists(state: CaseState) -> list[SpecialistReview]:
    """Review actual packet coverage without inventing absent feeds or diagnoses."""

    reviews = []
    for role_id, domains in ROLE_DOMAINS.items():
        signals = [signal for signal in state.signals if signal.domain in domains]
        sources = [source for source in state.source_coverage if source.domain in domains]
        present = {signal.domain for signal in signals if signal.observation_kind == "measurement"}
        present.update(source.domain for source in sources if source.observation_count > 0)
        reviews.append(SpecialistReview(
            role_id=role_id,
            responsibility=RESPONSIBILITIES[role_id],
            source_ids=sorted({signal.source_id for signal in signals} | {source.source_id for source in sources}),
            findings=[f"Reviewed {len(signals)} scenario signal(s) and {len(sources)} public source coverage record(s)."],
            gaps=[f"No supplied {domain.value} measurements; absence is not a negative finding." for domain in domains if domain not in present]
            + [f"{source.source_id}: {source.status.value}; {source.note}" for source in sources if source.status != SourceStatus.AVAILABLE],
        ))

    delayed = [signal for signal in state.signals if signal.reported_at is not None and signal.reported_at > signal.timestamp]
    unknown_times = sum(signal.reported_at is None for signal in state.signals)
    reviews.append(SpecialistReview(
        role_id="data_quality", responsibility=RESPONSIBILITIES["data_quality"],
        source_ids=sorted({signal.source_id for signal in state.signals} | {source.source_id for source in state.source_coverage}),
        findings=[f"{signal.signal_id}: reporting lag {(signal.reported_at - signal.timestamp).total_seconds() / 3600:.1f} hours." for signal in delayed],
        gaps=([f"Reporting time is unknown for {unknown_times} signal(s); do not assume immediate availability."] if unknown_times else [])
        + (["Public retrieval times do not establish publication delay or completeness."] if state.is_public else [])
        + ["Different source identifiers do not prove independent collection; shared upstream provenance requires analyst review."],
    ))
    for role_id, prefix in (("epidemiology", "EV-SPREAD-"), ("assessment", "EV-REPORT-")):
        evidence = [item for item in state.evidence if item.evidence_id.startswith(prefix)]
        reviews.append(SpecialistReview(
            role_id=role_id, responsibility=RESPONSIBILITIES[role_id],
            source_ids=sorted({source for item in evidence for source in item.source_ids}),
            findings=[item.finding for item in evidence],
            gaps=["No validated transmission forecast or laboratory-supported origin assessment is available in this prototype."],
        ))
    return reviews


def coordinate_verification(state: CaseState, candidates: list[dict[str, str]], selected_id: str) -> list[ProposedAction]:
    """Propose at most two checks that can proceed together, then a joint review."""

    selected = next(candidate for candidate in candidates if candidate["candidate_id"] == selected_id)
    checks = [selected]
    # Routine monitoring adds no independent verification to an active check.
    checks.extend(candidate for candidate in candidates if candidate["candidate_id"] not in {selected_id, "repeat-surveillance-review"})
    actions = []
    for candidate in checks[:2]:
        candidate_id = candidate["candidate_id"]
        actions.append(ProposedAction(
            action_id=f"ACT-{candidate_id.upper()}", title=candidate["recommendation"],
            owner=TASK_OWNERS[candidate_id], rationale=candidate["reason"], consequence="low",
            evidence_ids=[item.evidence_id for item in state.evidence],
            completion_criterion=candidate["question"] + " Record the source, event/reporting times and result, including unavailable or inconclusive outcomes.",
            review_trigger="Review when a source replies or at the next reporting interval; the human owner sets the deadline.",
        ))
    actions.append(ProposedAction(
        action_id="ACT-JOINT-REASSESSMENT", title="Reconcile verification results and update the shared assessment",
        owner="Designated incident coordinator with CDA and relevant agency liaisons",
        rationale="Combine returned findings, unresolved gaps and disagreement before proposing further action.",
        consequence="low", depends_on=[action.action_id for action in actions],
        evidence_ids=[item.evidence_id for item in state.evidence],
        completion_criterion="A human reviews returned or explicitly unavailable results and reruns the assessment with new evidence.",
        review_trigger="After verification outcomes are recorded, or earlier if a material new signal arrives.",
    ))
    return actions
