"""Behavioural acceptance checks for the BIO-SIGNAL slide workflow."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from backend.agent_functions import AGENT_FUNCTIONS
from backend.analytics import build_event_graph
from backend.coordination import acknowledge_action, assign_action, complete_action
from backend.hypothesis_scoring import estimate_confidence, score_hypotheses
from backend.orchestrator import BioSignalOrchestrator
from backend.public_sources import public_bundle_to_evidence
from backend.reporting import decide_action
from backend.scenario_loader import load_scenario
from backend.schemas import ActionStatus, Domain, PublicDataBundle, PublicObservation, RiskProfile, Signal, SourceStatus, TaskStatus
from tests.test_analytics import make_signal
from tests.test_public_sources import NOW, coverage, observation


def test_all_eight_functions_and_one_priority_are_visible():
    profile = BioSignalOrchestrator().run(load_scenario("contradictory_evidence"))
    assert {item.name for item in profile.agent_functions} == {
        "Sentinel", "Correlation", "Epidemiology", "Threat Assessment", "OSINT / External Intel",
        "Verification", "Coordination", "Briefing",
    }
    assert all(record.responsible_role in AGENT_FUNCTIONS for record in profile.tool_trace)
    primary = [action for action in profile.proposed_actions if action.action_id == profile.primary_verification_id]
    assert len(primary) == 1
    assert "CORROBORATE-EXTERNAL-REPORT" in primary[0].action_id
    assert primary[0].title in profile.executive_brief
    assert profile.known_findings[0].evidence_id in profile.executive_brief
    assert profile.impact.severity == "unassessed"


def test_graph_links_six_domains_but_context_does_not_establish_causality():
    signals = [make_signal(domain.value, domain, NOW) for domain in Domain]
    graph = build_event_graph(signals)
    assert len(graph.nodes) == 6
    assert len(graph.links) == 15
    for link in graph.links:
        is_context = bool({"mobility", "external"} & set(link.signal_ids))
        assert (link.relationship == "contextual_association") == is_context
    assert all(node.provenance and node.source_id for node in graph.nodes)
    assert "not causality" in graph.limitations


@pytest.mark.parametrize("mismatch", ["time", "location", "domain", "baseline"])
def test_graph_does_not_invent_links(mismatch):
    animal = make_signal("A", Domain.ANIMAL, NOW)
    human = make_signal("H", Domain.HUMAN, NOW + timedelta(hours=72))
    assert len(build_event_graph([animal, human]).links) == 1
    if mismatch == "time":
        human.timestamp += timedelta(seconds=1)
    elif mismatch == "location":
        human.location_cell = "GRID-OTHER"
    elif mismatch == "domain":
        human.domain = Domain.ANIMAL
    else:
        human.observed_value = human.baseline_mean
    assert not build_event_graph([animal, human]).links


def test_public_snapshot_does_not_fake_graph_epi_or_impact():
    profile = BioSignalOrchestrator().run_public(PublicDataBundle(retrieved_at=NOW))
    functions = {item.role_id: item for item in profile.agent_functions}
    assert functions["correlation"].status == functions["epidemiology"].status == "unavailable"
    assert not profile.event_graph.nodes and not profile.event_graph.links
    assert not profile.impact.affected_domains
    assert profile.impact.severity == "unassessed"
    assert profile.sensitivity == "public"


@pytest.mark.parametrize("source_id,domain", [
    ("NEA-DENGUE", Domain.HUMAN), ("NEA-ZIKA", Domain.HUMAN),
    ("DATA-GOV-WEATHER", Domain.ENVIRONMENTAL), ("CHANGI-TRAFFIC", Domain.MOBILITY),
    ("SFA-ALERTS", Domain.FOOD), ("WHO-DON", Domain.EXTERNAL),
])
def test_unlinked_public_context_does_not_shift_origin_or_confidence(source_id, domain):
    baseline = public_bundle_to_evidence(PublicDataBundle(retrieved_at=NOW))
    metric = "regional_outbreak_report" if source_id == "WHO-DON" else "unlinked_context"
    bundle = PublicDataBundle(retrieved_at=NOW,
        observations=[observation("CONTEXT", source_id, domain, metric, 1)],
        sources=[coverage(source_id, domain, SourceStatus.AVAILABLE, 1)])
    evidence = public_bundle_to_evidence(bundle)
    assert len(evidence) == len(baseline) + 1
    assert score_hypotheses(evidence) == score_hypotheses(baseline)
    assert estimate_confidence(score_hypotheses(evidence), evidence) == estimate_confidence(score_hypotheses(baseline), baseline)


def test_sensitivity_rejects_private_labels_before_model_selection():
    scenario = load_scenario("zoonotic_spillover")
    payload = scenario.initial_signals[0].model_dump()
    assert payload["sensitivity"] == "synthetic"
    payload["sensitivity"] = "restricted"
    with pytest.raises(ValidationError):
        Signal.model_validate(payload)
    public = observation("O", "CDA-WEEKLY", Domain.HUMAN, "count", 1).model_dump()
    assert public["sensitivity"] == "public"
    public["sensitivity"] = "restricted"
    with pytest.raises(ValidationError):
        PublicObservation.model_validate(public)
    scenario.initial_signals[0].sensitivity = "restricted"
    client = Mock(model_id="model")
    with pytest.raises(ValidationError):
        BioSignalOrchestrator(mode="live", decision_client=client).run(scenario)
    client.choose.assert_not_called()


def test_coordination_requires_approval_acknowledgement_result_and_deadline():
    profile = BioSignalOrchestrator().run(load_scenario("human_only_signal"))
    action = profile.proposed_actions[0]
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    with pytest.raises(ValueError, match="approval"):
        assign_action(profile, action.action_id, actor="Coordinator", due_at=future)
    decide_action(profile, action.action_id, True, actor="Reviewer")
    decide_action(profile, action.action_id, True, actor="Reviewer")
    assert len(profile.action_history) == 1
    with pytest.raises(ValueError, match="deadline"):
        assign_action(profile, action.action_id, actor="Coordinator", due_at=NOW.replace(tzinfo=None))
    assign_action(profile, action.action_id, actor="Coordinator", due_at=future)
    with pytest.raises(ValueError, match="Acknowledge"):
        complete_action(profile, action.action_id, actor="Owner", result="Inconclusive")
    acknowledge_action(profile, action.action_id, actor="Owner")
    with pytest.raises(ValueError, match="result"):
        complete_action(profile, action.action_id, actor="Owner", result=" ")
    scores = profile.hypotheses.copy()
    complete_action(profile, action.action_id, actor="Owner", result="Synthetic result unavailable; source liaison recorded no measurement.")
    assert profile.hypotheses == scores
    assert action.task_status == TaskStatus.COMPLETED
    assert action.assigned_at <= action.acknowledged_at <= action.completed_at
    assert action.due_at == future
    assert [event.event for event in profile.action_history] == ["approved", "assigned", "acknowledged", "completed"]
    assert RiskProfile.model_validate_json(profile.model_dump_json()) == profile
    with pytest.raises(ValueError):
        decide_action(profile, action.action_id, False)


def test_joint_review_cannot_start_until_all_dependencies_return():
    profile = BioSignalOrchestrator().run(load_scenario("contradictory_evidence"))
    joint = profile.proposed_actions[-1]
    future = datetime.now(timezone.utc) + timedelta(hours=3)
    decide_action(profile, joint.action_id, True)
    for action in profile.proposed_actions[:-1]:
        with pytest.raises(ValueError, match="prerequisite"):
            assign_action(profile, joint.action_id, actor="Coordinator", due_at=future)
        decide_action(profile, action.action_id, True)
        assign_action(profile, action.action_id, actor="Coordinator", due_at=future)
        acknowledge_action(profile, action.action_id, actor="Owner")
        complete_action(profile, action.action_id, actor="Owner", result="Synthetic source result is inconclusive.")
    assign_action(profile, joint.action_id, actor="Coordinator", due_at=future)
    assert joint.task_status == TaskStatus.ASSIGNED


def test_reassessment_keeps_identity_history_results_and_per_revision_limits():
    scenario = load_scenario("zoonotic_spillover")
    orchestrator = BioSignalOrchestrator()
    previous = orchestrator.run(scenario)
    action = previous.proposed_actions[0]
    decide_action(previous, action.action_id, True)
    updated = orchestrator.reassess(scenario, previous)
    assert updated.case_id == previous.case_id and updated.revision == 2
    assert updated.previous_assessments[0] == previous
    assert updated.previous_assessments[0] is not previous
    assert updated.previous_assessments[0].proposed_actions[0].status == ActionStatus.APPROVED
    assert all(item.status == ActionStatus.PENDING for item in updated.proposed_actions)
    assert not updated.action_history
    assert "SIG-E-001" in updated.change_log[-2]
    assert "support shifts:" in updated.change_log[-1]
    assert updated.metrics.completed_within_limits
    assert all(item.metrics.completed_within_limits for item in updated.previous_assessments)
    assert RiskProfile.model_validate_json(updated.model_dump_json()) == updated
    with pytest.raises(ValueError, match="already incorporated"):
        orchestrator.reassess(scenario, updated)
    scenario.initial_signals[0].observed_value += 1
    with pytest.raises(ValueError, match="initial evidence"):
        orchestrator.reassess(scenario, previous)


def test_ui_can_record_the_full_local_task_lifecycle_and_retain_decisions_on_update():
    from pathlib import Path
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "frontend" / "app.py")).run()
    next(button for button in app.button if button.label == "Start investigation").click().run()
    next(button for button in app.button if button.label == "Approve").click().run()
    next(button for button in app.button if button.label == "Assign locally").click().run()
    next(button for button in app.button if button.label == "Record acknowledgement").click().run()
    app.text_area[0].set_value("Synthetic laboratory liaison: paired results unavailable.").run()
    next(button for button in app.button if button.label == "Record completion").click().run()
    assert not app.exception
    assert app.session_state.profile.proposed_actions[0].task_status == TaskStatus.COMPLETED
    next(button for button in app.button if button.label == "Inject new synthetic evidence").click().run()
    assert not app.exception
    assert app.session_state.profile.previous_assessments[0].proposed_actions[0].result
    assert app.session_state.profile.proposed_actions[0].status == ActionStatus.PENDING
