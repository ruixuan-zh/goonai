"""Build a concise, evidence-linked risk profile from the case state."""

from __future__ import annotations

from .hypothesis_scoring import estimate_confidence, score_hypotheses
from .public_sources import critical_public_source_gaps
from .schemas import (
    ActionStatus,
    CaseState,
    CaseStatus,
    Confidence,
    Hypothesis,
    ProposedAction,
    RiskProfile,
    RunMetrics,
)


def estimate_sonnet_cost(input_tokens: int, output_tokens: int) -> float:
    """Conservative planning estimate, not a current tariff or billing control."""

    return round((input_tokens * 3.0 + output_tokens * 15.0) / 1_000_000, 6)


def _case_status(state: CaseState, leader: Hypothesis, confidence: Confidence) -> CaseStatus:
    has_cross_domain_match = any(
        item.evidence_id.startswith("EV-CORR-") and item.evidence_id != "EV-CORR-NONE"
        for item in state.evidence
    )
    has_unverified_report = any(
        item.finding.startswith("Uncorroborated external report") for item in state.evidence
    )
    if has_unverified_report or confidence == Confidence.LOW:
        return CaseStatus.VERIFY
    if leader == Hypothesis.NATURAL_ZOONOTIC and has_cross_domain_match:
        return CaseStatus.INVESTIGATE
    return CaseStatus.MONITOR


def _actions(status: CaseStatus, leader: Hypothesis) -> list[ProposedAction]:
    if status == CaseStatus.INVESTIGATE:
        return [
            ProposedAction(
                action_id="ACT-LAB-VERIFY",
                title="Request cross-agency laboratory verification",
                owner="Public-health duty officer",
                rationale=(
                    f"The leading screening hypothesis is {leader.value}; laboratory confirmation "
                    "is required before attribution or escalation."
                ),
                consequence="medium",
            )
        ]
    if status == CaseStatus.VERIFY:
        return [
            ProposedAction(
                action_id="ACT-SOURCE-VERIFY",
                title="Seek an independent source and laboratory check",
                owner="Surveillance analyst",
                rationale="Material uncertainty or contradictory reporting prevents a confident assessment.",
                consequence="low",
            )
        ]
    return [
        ProposedAction(
            action_id="ACT-MONITOR",
            title="Continue routine surveillance monitoring",
            owner="Surveillance analyst",
            rationale="Current evidence does not justify exceptional escalation.",
            consequence="low",
        )
    ]


def build_risk_profile(
    state: CaseState,
    *,
    max_model_calls: int,
    max_tool_calls: int,
) -> RiskProfile:
    assessments = score_hypotheses(state.evidence)
    confidence = estimate_confidence(assessments, state.evidence)
    missing_critical_public_domains = state.is_public and critical_public_source_gaps(state.source_coverage)
    if missing_critical_public_domains and confidence == Confidence.HIGH:
        confidence = Confidence.MEDIUM
    if state.is_public and not any(
        item.evidence_id != "EV-PUBLIC-COVERAGE-GAPS" for item in state.evidence
    ):
        confidence = Confidence.LOW
    leader = assessments[0].hypothesis
    status = _case_status(state, leader, confidence)
    uncertainty = list(dict.fromkeys(state.open_questions))
    if not uncertainty:
        uncertainty = [
            "The synthetic observations have not been confirmed by laboratory diagnostics.",
            "Support scores describe relative evidence in this demonstration and are not probabilities.",
        ]
    checks = list(dict.fromkeys(state.recommended_verification))
    if not checks:
        checks = ["Obtain laboratory confirmation and an independent epidemiological source."]
    return RiskProfile(
        case_id=state.case_id,
        scenario_id=state.scenario_id,
        scenario_title=state.scenario_title,
        status=status,
        confidence=confidence,
        leading_hypothesis=leader,
        hypotheses=assessments,
        known_findings=state.evidence,
        uncertainty=uncertainty,
        recommended_verification=checks,
        proposed_actions=_actions(status, leader),
        tool_trace=state.tool_trace,
        change_log=state.change_log,
        metrics=RunMetrics(
            model_calls=state.model_calls,
            tool_calls=len(state.tool_trace),
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            estimated_cost_usd=estimate_sonnet_cost(state.input_tokens, state.output_tokens),
            fallback_used=state.fallback_used,
            completed_within_limits=(
                state.model_calls <= max_model_calls and len(state.tool_trace) <= max_tool_calls
            ),
        ),
        source_coverage=state.source_coverage,
    )


def decide_action(profile: RiskProfile, action_id: str, approved: bool) -> RiskProfile:
    """Record a human decision; the system never dispatches an action itself."""

    matching = [action for action in profile.proposed_actions if action.action_id == action_id]
    if not matching:
        raise ValueError(f"Unknown action: {action_id}")
    matching[0].status = ActionStatus.APPROVED if approved else ActionStatus.REJECTED
    return profile
