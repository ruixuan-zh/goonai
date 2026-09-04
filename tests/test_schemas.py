from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from backend.schemas import Domain, Signal


def valid_signal(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "signal_id": "SIG-TEST",
        "timestamp": datetime.now(timezone.utc),
        "domain": Domain.HUMAN,
        "location_cell": "GRID-01",
        "signal_type": "presentations",
        "observed_value": 10,
        "baseline_mean": 5,
        "baseline_std": 2,
        "unit": "count",
        "source_id": "SYN-SOURCE",
        "source_confidence": 0.8,
        "provenance": "Synthetic unit-test fixture.",
        "synthetic": True,
    }
    payload.update(overrides)
    return payload


class SignalSchemaTests(unittest.TestCase):
    def test_valid_signal_is_accepted(self) -> None:
        signal = Signal.model_validate(valid_signal())
        self.assertEqual(signal.domain, Domain.HUMAN)

    def test_source_confidence_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            Signal.model_validate(valid_signal(source_confidence=1.2))

    def test_standard_deviation_must_be_positive(self) -> None:
        with self.assertRaises(ValidationError):
            Signal.model_validate(valid_signal(baseline_std=0))

    def test_non_synthetic_operational_data_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            Signal.model_validate(valid_signal(synthetic=False))


if __name__ == "__main__":
    unittest.main()
