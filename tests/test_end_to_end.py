from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from backend.orchestrator import BedrockDecisionClient, BioSignalOrchestrator, Decision, ModelResult
from backend.reporting import decide_action, estimate_sonnet_cost
from backend.scenario_loader import available_scenarios, load_scenario
from backend.schemas import ActionStatus, Hypothesis


class FakeBedrockClient:
    model_id = "fake-sonnet-5"

    def choose(self, packet: dict[str, Any], available_tools: list[str]) -> ModelResult:
        priority = [
            "correlate_signals",
            "assess_spread_plausibility",
            "verify_external_report",
            "recommend_next_check",
            "finish_investigation",
        ]
        selected = next(name for name in priority if name in available_tools)
        tool_input: dict[str, Any] = {
            "rationale": f"Select {selected} for the next bounded check."
        }
        if selected == "recommend_next_check":
            candidates = packet["verification_candidates"]
            tool_input["candidate_id"] = candidates[0]["candidate_id"]
        return ModelResult(Decision(selected, tool_input), input_tokens=120, output_tokens=15)


class FakeBedrockRuntime:
    def __init__(self) -> None:
        self.request: dict[str, object] = {}

    def converse(self, **kwargs: object) -> dict[str, object]:
        self.request = kwargs
        return {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "correlate_signals",
                                "input": {"rationale": "Check the available cross-domain signals."},
                            }
                        }
                    ]
                }
            },
            "usage": {"inputTokens": 90, "outputTokens": 12},
        }


class EndToEndTests(unittest.TestCase):
    def test_every_scenario_matches_expected_screening_outcome(self) -> None:
        self.assertEqual(
            set(available_scenarios()),
            {
                "contradictory_evidence",
                "geographic_mismatch",
                "human_only_signal",
                "imported_outbreak_context",
                "seasonal_outbreak",
                "zoonotic_spillover",
            },
        )
        for name in available_scenarios():
            with self.subTest(scenario=name):
                scenario = load_scenario(name)
                profile = BioSignalOrchestrator(mode="replay").run(scenario)
                self.assertEqual(profile.leading_hypothesis, scenario.expected_leading_hypothesis)
                self.assertEqual(profile.status, scenario.expected_status)
                self.assertTrue(profile.metrics.completed_within_limits)
                self.assertLessEqual(profile.metrics.tool_calls, 6)
                self.assertTrue(all(record.success for record in profile.tool_trace))

    def test_evidence_and_claims_remain_traceable(self) -> None:
        profile = BioSignalOrchestrator(mode="replay").run(load_scenario("zoonotic_spillover"))
        evidence_ids = [item.evidence_id for item in profile.known_findings]
        self.assertEqual(len(evidence_ids), len(set(evidence_ids)))
        referenced_ids = {
            evidence_id
            for assessment in profile.hypotheses
            for evidence_id in assessment.evidence_for + assessment.evidence_against
        }
        self.assertTrue(referenced_ids.issubset(set(evidence_ids)))
        self.assertNotEqual(profile.leading_hypothesis, Hypothesis.DELIBERATE_RELEASE)

    def test_actions_require_a_human_decision(self) -> None:
        profile = BioSignalOrchestrator(mode="replay").run(load_scenario("zoonotic_spillover"))
        action = profile.proposed_actions[0]
        self.assertEqual(action.status, ActionStatus.PENDING)
        decide_action(profile, action.action_id, True)
        self.assertEqual(action.status, ActionStatus.APPROVED)

    def test_evidence_injection_is_recorded(self) -> None:
        scenario = load_scenario("zoonotic_spillover")
        profile = BioSignalOrchestrator(mode="replay").run(scenario, include_new_evidence=True)
        self.assertTrue(profile.change_log)
        self.assertTrue(any(item.evidence_id == "EV-REPORT-SIG-E-001" for item in profile.known_findings))

    def test_next_check_adapts_to_the_material_evidence_gap(self) -> None:
        expected_candidate = {
            "contradictory_evidence": "corroborate-external-report",
            "seasonal_outbreak": "repeat-surveillance-review",
            "zoonotic_spillover": "paired-laboratory-confirmation",
        }
        for scenario_name, candidate_id in expected_candidate.items():
            with self.subTest(scenario=scenario_name):
                profile = BioSignalOrchestrator(mode="replay").run(load_scenario(scenario_name))
                recommendation_step = next(
                    record
                    for record in profile.tool_trace
                    if record.tool_name == "recommend_next_check"
                )
                self.assertEqual(recommendation_step.tool_input["candidate_id"], candidate_id)
                self.assertIn("Decision rationale:", recommendation_step.summary)

    def test_live_path_tracks_calls_tokens_and_cost(self) -> None:
        orchestrator = BioSignalOrchestrator(
            mode="live",
            decision_client=FakeBedrockClient(),
            max_model_calls=4,
            fallback_to_replay=False,
        )
        profile = orchestrator.run(load_scenario("zoonotic_spillover"))
        self.assertEqual(profile.metrics.model_calls, 4)
        self.assertEqual(profile.metrics.input_tokens, 480)
        self.assertEqual(profile.metrics.output_tokens, 60)
        self.assertEqual(profile.metrics.estimated_cost_usd, estimate_sonnet_cost(480, 60))

    def test_live_client_initialisation_can_fall_back_to_replay(self) -> None:
        with patch.object(BioSignalOrchestrator, "_make_client", side_effect=RuntimeError("no credentials")):
            orchestrator = BioSignalOrchestrator(mode="live", fallback_to_replay=True)
        profile = orchestrator.run(load_scenario("zoonotic_spillover"))
        self.assertTrue(profile.metrics.fallback_used)
        self.assertEqual(profile.metrics.model_calls, 0)

    def test_bedrock_converse_response_is_parsed_as_a_tool_decision(self) -> None:
        runtime = FakeBedrockRuntime()
        client = object.__new__(BedrockDecisionClient)
        client._client = runtime
        client.model_id = "global.anthropic.claude-sonnet-5"
        client.max_output_tokens = 300
        result = client.choose({"case_id": "BIO-TEST"}, ["correlate_signals"])
        self.assertEqual(result.decision.tool_name, "correlate_signals")
        self.assertTrue(result.decision.tool_input["rationale"])
        self.assertEqual(result.input_tokens, 90)
        self.assertEqual(result.output_tokens, 12)
        self.assertEqual(runtime.request["modelId"], "global.anthropic.claude-sonnet-5")


if __name__ == "__main__":
    unittest.main()
