"""Transparent, deterministic support scoring for competing hypotheses."""

from __future__ import annotations

from .schemas import Confidence, Evidence, Hypothesis, HypothesisAssessment


BASE_SUPPORT = {
    Hypothesis.NATURAL_ZOONOTIC: 25.0,
    Hypothesis.ACCIDENTAL_RELEASE: 15.0,
    Hypothesis.DELIBERATE_RELEASE: 10.0,
    Hypothesis.INSUFFICIENT_EVIDENCE: 30.0,
}


def score_hypotheses(evidence: list[Evidence]) -> list[HypothesisAssessment]:
    """Normalise weighted support to 100; scores are decision aids, not probabilities."""

    raw = dict(BASE_SUPPORT)
    for item in evidence:
        for hypothesis, effect in item.hypothesis_effects.items():
            raw[hypothesis] += effect * item.quality
    raw = {hypothesis: max(1.0, value) for hypothesis, value in raw.items()}
    total = sum(raw.values())
    rounded = {hypothesis: round(value / total * 100) for hypothesis, value in raw.items()}
    difference = 100 - sum(rounded.values())
    leader = max(raw, key=raw.get)
    rounded[leader] += difference

    assessments: list[HypothesisAssessment] = []
    for hypothesis in Hypothesis:
        evidence_for = [
            item.evidence_id for item in evidence if item.hypothesis_effects.get(hypothesis, 0) > 0
        ]
        evidence_against = [
            item.evidence_id for item in evidence if item.hypothesis_effects.get(hypothesis, 0) < 0
        ]
        assessments.append(
            HypothesisAssessment(
                hypothesis=hypothesis,
                support_score=rounded[hypothesis],
                evidence_for=evidence_for,
                evidence_against=evidence_against,
            )
        )
    return sorted(assessments, key=lambda item: item.support_score, reverse=True)


def estimate_confidence(
    assessments: list[HypothesisAssessment], evidence: list[Evidence]
) -> Confidence:
    if not evidence:
        return Confidence.LOW
    margin = assessments[0].support_score - assessments[1].support_score
    independent_sources = {source for item in evidence for source in item.source_ids}
    mean_quality = sum(item.quality for item in evidence) / len(evidence)
    if margin >= 25 and len(independent_sources) >= 2 and mean_quality >= 0.75:
        return Confidence.HIGH
    if margin >= 10 and mean_quality >= 0.55:
        return Confidence.MEDIUM
    return Confidence.LOW
