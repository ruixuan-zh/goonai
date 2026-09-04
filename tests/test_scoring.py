from __future__ import annotations

import unittest

from backend.hypothesis_scoring import score_hypotheses
from backend.schemas import Evidence, Hypothesis


class ScoringTests(unittest.TestCase):
    def test_scores_sum_to_one_hundred(self) -> None:
        assessments = score_hypotheses([])
        self.assertEqual(sum(item.support_score for item in assessments), 100)

    def test_weighted_evidence_changes_leading_hypothesis(self) -> None:
        evidence = [
            Evidence(
                evidence_id="EV-1",
                finding="Synthetic linked animal and human signal.",
                source_ids=["SYN-A", "SYN-H"],
                quality=0.9,
                hypothesis_effects={
                    Hypothesis.NATURAL_ZOONOTIC: 50,
                    Hypothesis.ACCIDENTAL_RELEASE: 0,
                    Hypothesis.DELIBERATE_RELEASE: 0,
                    Hypothesis.INSUFFICIENT_EVIDENCE: -10,
                },
                limitations="Unit-test fixture only.",
            )
        ]
        assessments = score_hypotheses(evidence)
        self.assertEqual(assessments[0].hypothesis, Hypothesis.NATURAL_ZOONOTIC)
        self.assertIn("EV-1", assessments[0].evidence_for)


if __name__ == "__main__":
    unittest.main()
