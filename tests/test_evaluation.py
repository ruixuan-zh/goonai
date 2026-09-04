from __future__ import annotations

import unittest

from backend.evaluate import evaluate_replay_suite


class EvaluationTests(unittest.TestCase):
    def test_replay_baseline_is_complete_safe_and_reproducible(self) -> None:
        report = evaluate_replay_suite()
        summary = report["summary"]

        self.assertEqual(report["scenario_count"], 6)
        self.assertEqual(summary["expected_hypothesis_match_rate"], 1.0)
        self.assertEqual(summary["expected_status_match_rate"], 1.0)
        self.assertEqual(summary["task_completion_rate"], 1.0)
        self.assertEqual(summary["tool_call_success_rate"], 1.0)
        self.assertEqual(summary["tool_rationale_completeness_rate"], 1.0)
        self.assertEqual(summary["verification_recommendation_rate"], 1.0)
        self.assertEqual(summary["evidence_provenance_completeness_rate"], 1.0)
        self.assertEqual(summary["limit_violation_count"], 0)
        self.assertEqual(summary["automatic_action_count"], 0)


if __name__ == "__main__":
    unittest.main()
