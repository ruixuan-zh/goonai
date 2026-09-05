from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from backend.analytics import calculate_z_score, correlate_signals, detect_anomalies
from backend.schemas import Domain, Signal


def make_signal(signal_id: str, domain: Domain, timestamp: datetime, location: str = "GRID-X") -> Signal:
    return Signal(
        signal_id=signal_id,
        timestamp=timestamp,
        domain=domain,
        location_cell=location,
        signal_type="test_count",
        observed_value=10,
        baseline_mean=2,
        baseline_std=2,
        unit="count",
        source_id=f"SYN-{signal_id}",
        source_confidence=0.8,
        provenance="Synthetic unit-test fixture.",
        synthetic=True,
    )


class AnalyticsTests(unittest.TestCase):
    def test_z_score_and_anomaly_detection(self) -> None:
        signal = make_signal("A", Domain.ANIMAL, datetime.now(timezone.utc))
        self.assertEqual(calculate_z_score(signal), 4.0)
        self.assertEqual(detect_anomalies([signal]), [signal])

    def test_cross_domain_pair_is_correlated_within_window(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        animal = make_signal("A", Domain.ANIMAL, start)
        human = make_signal("H", Domain.HUMAN, start + timedelta(hours=24))
        evidence = correlate_signals([animal, human])
        self.assertEqual(len(evidence), 1)
        self.assertTrue(evidence[0].evidence_id.startswith("EV-CORR-"))
        self.assertIn("within 24 hours", evidence[0].finding)

    def test_location_mismatch_does_not_correlate(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        animal = make_signal("A", Domain.ANIMAL, start, "GRID-A")
        human = make_signal("H", Domain.HUMAN, start, "GRID-B")
        evidence = correlate_signals([animal, human])
        self.assertEqual(evidence[0].evidence_id, "EV-CORR-NONE")


if __name__ == "__main__":
    unittest.main()
