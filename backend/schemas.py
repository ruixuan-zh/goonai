"""Validated data contracts shared by the BIO-SIGNAL pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Domain(StrEnum):
    HUMAN = "human"
    ANIMAL = "animal"
    ENVIRONMENTAL = "environmental"
    FOOD = "food"
    MOBILITY = "mobility"
    EXTERNAL = "external"


class Hypothesis(StrEnum):
    NATURAL_ZOONOTIC = "natural_zoonotic"
    ACCIDENTAL_RELEASE = "accidental_release"
    DELIBERATE_RELEASE = "deliberate_release"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CaseStatus(StrEnum):
    MONITOR = "monitor"
    INVESTIGATE = "investigate"
    VERIFY = "verify"


class ActionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SourceStatus(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    CONTEXT_ONLY = "context_only"
    UNAVAILABLE = "unavailable"


class Signal(BaseModel):
    """A normalised surveillance observation; scenarios must be synthetic."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str
    timestamp: datetime
    domain: Domain
    location_cell: str
    signal_type: str
    observed_value: float
    baseline_mean: float
    baseline_std: float = Field(gt=0)
    unit: str
    source_id: str
    source_confidence: float = Field(ge=0, le=1)
    provenance: str
    synthetic: bool = True
    report_summary: str | None = None
    corroborated: bool | None = None

    @field_validator("synthetic")
    @classmethod
    def require_synthetic_data(cls, value: bool) -> bool:
        if not value:
            raise ValueError("The prototype accepts synthetic scenario data only")
        return value


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    finding: str
    source_ids: list[str]
    quality: float = Field(ge=0, le=1)
    hypothesis_effects: dict[Hypothesis, float]
    limitations: str


class PublicObservation(BaseModel):
    """A non-sensitive aggregate observation retrieved from an allow-listed public source."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str
    observed_at: datetime
    domain: Domain
    metric: str
    value: float
    unit: str
    geography_scope: str = "Singapore"
    baseline_value: float | None = None
    baseline_description: str | None = None
    source_id: str
    source_url: str
    source_confidence: float = Field(ge=0, le=1)
    summary: str
    limitations: str


class SourceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    publisher: str
    title: str
    url: str
    domain: Domain
    status: SourceStatus
    retrieved_at: datetime
    observation_count: int = Field(ge=0)
    cadence: str
    note: str


class PublicDataBundle(BaseModel):
    retrieved_at: datetime
    geography_scope: str = "Singapore"
    observations: list[PublicObservation] = Field(default_factory=list)
    sources: list[SourceCoverage] = Field(default_factory=list)


class HypothesisAssessment(BaseModel):
    hypothesis: Hypothesis
    support_score: int = Field(ge=0, le=100)
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    sequence: int = Field(ge=1)
    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)
    success: bool
    summary: str
    latency_ms: int = Field(ge=0)
    model_id: str | None = None


class ProposedAction(BaseModel):
    action_id: str
    title: str
    owner: str
    rationale: str
    consequence: str
    status: ActionStatus = ActionStatus.PENDING


class RunMetrics(BaseModel):
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    fallback_used: bool = False
    completed_within_limits: bool = True


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    title: str
    description: str
    data_notice: str
    initial_signals: list[Signal]
    new_evidence_signals: list[Signal] = Field(default_factory=list)
    expected_leading_hypothesis: Hypothesis
    expected_status: CaseStatus


class CaseState(BaseModel):
    case_id: str
    scenario_id: str
    scenario_title: str
    signals: list[Signal]
    evidence: list[Evidence] = Field(default_factory=list)
    executed_tools: list[str] = Field(default_factory=list)
    tool_trace: list[ToolCallRecord] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    recommended_verification: list[str] = Field(default_factory=list)
    change_log: list[str] = Field(default_factory=list)
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    fallback_used: bool = False
    source_coverage: list[SourceCoverage] = Field(default_factory=list)


class RiskProfile(BaseModel):
    case_id: str
    scenario_id: str
    scenario_title: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: CaseStatus
    confidence: Confidence
    leading_hypothesis: Hypothesis
    hypotheses: list[HypothesisAssessment]
    known_findings: list[Evidence]
    uncertainty: list[str]
    recommended_verification: list[str]
    proposed_actions: list[ProposedAction]
    tool_trace: list[ToolCallRecord]
    change_log: list[str] = Field(default_factory=list)
    metrics: RunMetrics
    source_coverage: list[SourceCoverage] = Field(default_factory=list)
