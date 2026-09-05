"""Deterministic analytical tools exposed to the orchestrator."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from .schemas import Domain, Evidence, Hypothesis, Signal


ANOMALY_THRESHOLD = 2.0


def calculate_z_score(signal: Signal) -> float:
    return (signal.observed_value - signal.baseline_mean) / signal.baseline_std


def detect_anomalies(signals: list[Signal], threshold: float = ANOMALY_THRESHOLD) -> list[Signal]:
    return [signal for signal in signals if calculate_z_score(signal) >= threshold]


def anomaly_evidence(signals: list[Signal]) -> list[Evidence]:
    """Create transparent evidence records from statistically unusual signals."""

    records: list[Evidence] = []
    for signal in detect_anomalies(signals):
        effects = {
            Hypothesis.NATURAL_ZOONOTIC: 7.0 if signal.domain == Domain.HUMAN else 9.0,
            Hypothesis.ACCIDENTAL_RELEASE: 2.0,
            Hypothesis.DELIBERATE_RELEASE: 1.0,
            Hypothesis.INSUFFICIENT_EVIDENCE: -2.0,
        }
        if signal.domain == Domain.EXTERNAL:
            effects = {hypothesis: 0.0 for hypothesis in Hypothesis}
        records.append(
            Evidence(
                evidence_id=f"EV-ANOM-{signal.signal_id}",
                finding=(
                    f"{signal.signal_type} in {signal.location_cell} is "
                    f"{calculate_z_score(signal):.1f} standard deviations above its synthetic baseline."
                ),
                source_ids=[signal.source_id],
                quality=signal.source_confidence,
                hypothesis_effects=effects,
                limitations="A baseline anomaly is a screening signal, not proof of cause or attribution.",
            )
        )
    return records


def correlate_signals(signals: list[Signal], maximum_gap_hours: int = 72) -> list[Evidence]:
    """Find human/animal anomaly pairs in the same coarse location and time window."""

    anomalous = detect_anomalies(signals)
    humans = [signal for signal in anomalous if signal.domain == Domain.HUMAN]
    animals = [signal for signal in anomalous if signal.domain == Domain.ANIMAL]
    matches: list[Evidence] = []
    maximum_gap = timedelta(hours=maximum_gap_hours)
    for animal in animals:
        for human in humans:
            gap = abs(human.timestamp - animal.timestamp)
            if animal.location_cell == human.location_cell and gap <= maximum_gap:
                matches.append(
                    Evidence(
                        evidence_id=f"EV-CORR-{animal.signal_id}-{human.signal_id}",
                        finding=(
                            f"Animal and human anomalies co-occurred in {animal.location_cell} "
                            f"within {gap.total_seconds() / 3600:.0f} hours."
                        ),
                        source_ids=[animal.source_id, human.source_id],
                        quality=min(animal.source_confidence, human.source_confidence),
                        hypothesis_effects={
                            Hypothesis.NATURAL_ZOONOTIC: 28.0,
                            Hypothesis.ACCIDENTAL_RELEASE: 7.0,
                            Hypothesis.DELIBERATE_RELEASE: 4.0,
                            Hypothesis.INSUFFICIENT_EVIDENCE: -10.0,
                        },
                        limitations="Spatiotemporal association does not establish transmission direction or pathogen identity.",
                    )
                )
    if matches:
        return matches
    return [
        Evidence(
            evidence_id="EV-CORR-NONE",
            finding=f"No signal-level cross-domain anomaly pair met the {maximum_gap_hours}-hour and same-location screening rule.",
            source_ids=sorted({signal.source_id for signal in anomalous}),
            quality=0.75,
            hypothesis_effects={
                Hypothesis.NATURAL_ZOONOTIC: -8.0,
                Hypothesis.ACCIDENTAL_RELEASE: -3.0,
                Hypothesis.DELIBERATE_RELEASE: -3.0,
                Hypothesis.INSUFFICIENT_EVIDENCE: 16.0,
            },
            limitations="Absence of a detected pair may reflect incomplete or delayed surveillance.",
        )
    ]


def assess_spread_plausibility(signals: list[Signal]) -> list[Evidence]:
    """Evaluate whether the observed order is consistent with animal-to-human spillover."""

    anomalous = detect_anomalies(signals)
    humans = [signal for signal in anomalous if signal.domain == Domain.HUMAN]
    animals = [signal for signal in anomalous if signal.domain == Domain.ANIMAL]
    plausible_pairs = [
        (animal, human)
        for animal in animals
        for human in humans
        if animal.location_cell == human.location_cell
        and animal.timestamp < human.timestamp
        and human.timestamp - animal.timestamp <= timedelta(hours=72)
    ]
    if plausible_pairs:
        animal, human = min(plausible_pairs, key=lambda pair: pair[1].timestamp - pair[0].timestamp)
        gap = human.timestamp - animal.timestamp
        return [
            Evidence(
                evidence_id=f"EV-SPREAD-{animal.signal_id}-{human.signal_id}",
                finding=(
                    "The synthetic animal anomaly preceded the linked human anomaly by "
                    f"{gap.total_seconds() / 3600:.0f} hours, consistent with a spillover hypothesis."
                ),
                source_ids=[animal.source_id, human.source_id],
                quality=min(animal.source_confidence, human.source_confidence) * 0.9,
                hypothesis_effects={
                    Hypothesis.NATURAL_ZOONOTIC: 30.0,
                    Hypothesis.ACCIDENTAL_RELEASE: -4.0,
                    Hypothesis.DELIBERATE_RELEASE: -5.0,
                    Hypothesis.INSUFFICIENT_EVIDENCE: -8.0,
                },
                limitations="Temporal ordering alone cannot demonstrate an epidemiological transmission chain.",
            )
        ]
    return [
        Evidence(
            evidence_id="EV-SPREAD-UNRESOLVED",
            finding="The available signals do not establish a plausible animal-to-human temporal sequence.",
            source_ids=sorted({signal.source_id for signal in anomalous}),
            quality=0.7,
            hypothesis_effects={
                Hypothesis.NATURAL_ZOONOTIC: -5.0,
                Hypothesis.ACCIDENTAL_RELEASE: 0.0,
                Hypothesis.DELIBERATE_RELEASE: 0.0,
                Hypothesis.INSUFFICIENT_EVIDENCE: 12.0,
            },
            limitations="Surveillance timestamps can lag the underlying biological events.",
        )
    ]


def verify_external_reports(signals: list[Signal]) -> list[Evidence]:
    """Turn external reports into weighted evidence without treating text as fact."""

    reports = [signal for signal in signals if signal.domain == Domain.EXTERNAL]
    if not reports:
        return [
            Evidence(
                evidence_id="EV-REPORT-NONE",
                finding="No external report is present in the scenario packet.",
                source_ids=[],
                quality=1.0,
                hypothesis_effects={hypothesis: 0.0 for hypothesis in Hypothesis},
                limitations="This check says nothing about reports that were not included in the scenario.",
            )
        ]
    evidence: list[Evidence] = []
    for report in reports:
        summary = report.report_summary or "An external surveillance report was supplied."
        if report.corroborated:
            effects = {
                Hypothesis.NATURAL_ZOONOTIC: 12.0,
                Hypothesis.ACCIDENTAL_RELEASE: 1.0,
                Hypothesis.DELIBERATE_RELEASE: 0.0,
                Hypothesis.INSUFFICIENT_EVIDENCE: -4.0,
            }
            finding = f"Corroborated external report: {summary}"
        else:
            effects = {
                Hypothesis.NATURAL_ZOONOTIC: -2.0,
                Hypothesis.ACCIDENTAL_RELEASE: 0.0,
                Hypothesis.DELIBERATE_RELEASE: 0.0,
                Hypothesis.INSUFFICIENT_EVIDENCE: 15.0,
            }
            finding = f"Uncorroborated external report: {summary}"
        evidence.append(
            Evidence(
                evidence_id=f"EV-REPORT-{report.signal_id}",
                finding=finding,
                source_ids=[report.source_id],
                quality=report.source_confidence,
                hypothesis_effects=effects,
                limitations="External reporting is retained as a claim until independently verified.",
            )
        )
    return evidence


ANALYTICAL_TOOLS: dict[str, Callable[[list[Signal]], list[Evidence]]] = {
    "correlate_signals": correlate_signals,
    "assess_spread_plausibility": assess_spread_plausibility,
    "verify_external_report": verify_external_reports,
}
