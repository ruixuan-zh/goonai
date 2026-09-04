from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.orchestrator import BioSignalOrchestrator
from backend.public_sources import PublicSourceClient, PublicSourceError, public_bundle_to_evidence
from backend.schemas import (
    Domain,
    PublicDataBundle,
    PublicObservation,
    SourceCoverage,
    SourceStatus,
)


NOW = datetime(2026, 9, 4, tzinfo=timezone.utc)


def observation(
    observation_id: str,
    source_id: str,
    domain: Domain,
    metric: str,
    value: float,
    baseline: float | None = None,
) -> PublicObservation:
    return PublicObservation(
        observation_id=observation_id,
        observed_at=NOW,
        domain=domain,
        metric=metric,
        value=value,
        unit="count",
        baseline_value=baseline,
        baseline_description="Public comparison median" if baseline is not None else None,
        source_id=source_id,
        source_url="https://www.cda.gov.sg/resources/",
        source_confidence=0.95,
        summary=f"{metric}: {value:g}",
        limitations="Aggregate test fixture.",
    )


def coverage(
    source_id: str,
    domain: Domain,
    status: SourceStatus,
    count: int,
) -> SourceCoverage:
    return SourceCoverage(
        source_id=source_id,
        publisher="Singapore public organisation",
        title=source_id,
        url="https://www.cda.gov.sg/resources/",
        domain=domain,
        status=status,
        retrieved_at=NOW,
        observation_count=count,
        cadence="Test cadence",
        note="Test fixture.",
    )


class PublicSourceTests(unittest.TestCase):
    def test_http_client_rejects_non_allow_listed_hosts(self) -> None:
        with self.assertRaises(PublicSourceError):
            PublicSourceClient._validated_url("https://example.com/untrusted")

    def test_bundle_compacts_all_domains_and_exposes_critical_gaps(self) -> None:
        bundle = PublicDataBundle(
            retrieved_at=NOW,
            observations=[
                observation("CDA-1", "CDA-WEEKLY", Domain.HUMAN, "avian_influenza", 5, 0),
                observation("NEA-1", "NEA-DENGUE", Domain.HUMAN, "dengue_weekly_cases", 80),
                observation("ENV-1", "DATA-GOV-WEATHER", Domain.ENVIRONMENTAL, "rainfall_mean", 2),
                observation("MOB-1", "CHANGI-TRAFFIC", Domain.MOBILITY, "passengers", 5_000_000),
            ],
            sources=[
                coverage("CDA-WEEKLY", Domain.HUMAN, SourceStatus.AVAILABLE, 1),
                coverage("NEA-DENGUE", Domain.HUMAN, SourceStatus.AVAILABLE, 1),
                coverage("DATA-GOV-WEATHER", Domain.ENVIRONMENTAL, SourceStatus.AVAILABLE, 1),
                coverage("CHANGI-TRAFFIC", Domain.MOBILITY, SourceStatus.AVAILABLE, 1),
                coverage("AVS-BIOSURVEILLANCE", Domain.ANIMAL, SourceStatus.CONTEXT_ONLY, 0),
                coverage("NEA-WASTEWATER", Domain.ENVIRONMENTAL, SourceStatus.CONTEXT_ONLY, 0),
            ],
        )
        evidence = public_bundle_to_evidence(bundle)
        evidence_ids = {item.evidence_id for item in evidence}
        self.assertIn("EV-PUBLIC-CDA-WEEKLY", evidence_ids)
        self.assertIn("EV-PUBLIC-COVERAGE-GAPS", evidence_ids)
        self.assertLessEqual(len(evidence), 8)

    def test_public_bundle_runs_through_bounded_agent_and_preserves_sources(self) -> None:
        bundle = PublicDataBundle(
            retrieved_at=NOW,
            observations=[
                observation("CDA-1", "CDA-WEEKLY", Domain.HUMAN, "acute_respiratory", 2600, 2400)
            ],
            sources=[coverage("CDA-WEEKLY", Domain.HUMAN, SourceStatus.AVAILABLE, 1)],
        )
        profile = BioSignalOrchestrator(mode="replay").run_public(bundle)
        self.assertEqual(profile.scenario_id, "singapore_public_snapshot")
        self.assertEqual(profile.source_coverage[0].source_id, "CDA-WEEKLY")
        self.assertTrue(profile.metrics.completed_within_limits)
        self.assertLessEqual(profile.metrics.tool_calls, 6)


if __name__ == "__main__":
    unittest.main()
