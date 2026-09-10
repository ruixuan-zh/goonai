"""Validated data contracts shared by the goonai pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


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


class TaskStatus(StrEnum):
    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"


class SourceStatus(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    CONTEXT_ONLY = "context_only"
    UNAVAILABLE = "unavailable"


class Signal(BaseModel):
    """A normalised surveillance observation; scenarios must be synthetic."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_min_length=1)

    signal_id: str
    timestamp: AwareDatetime
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
    synthetic: bool = Field(strict=True)
    sensitivity: Literal["synthetic"] = "synthetic"
    report_summary: str | None = None
    corroborated: bool | None = None
    reported_at: AwareDatetime | None = None
    observation_kind: str = Field(default="measurement", pattern="^(measurement|behavioural_context)$")

    @model_validator(mode="after")
    def validate_reporting_time(self) -> Signal:
        if self.reported_at is not None and self.reported_at < self.timestamp:
            raise ValueError("reported_at cannot precede the observation timestamp")
        return self

    @field_validator("synthetic")
    @classmethod
    def require_synthetic_data(cls, value: bool) -> bool:
        if not value:
            raise ValueError("The prototype accepts synthetic scenario data only")
        return value


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_min_length=1)

    evidence_id: str
    finding: str
    source_ids: list[str]
    quality: float = Field(ge=0, le=1)
    hypothesis_effects: dict[Hypothesis, float]
    limitations: str


class PublicObservation(BaseModel):
    """A non-sensitive aggregate observation retrieved from an allow-listed public source."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_min_length=1)

    observation_id: str
    observed_at: AwareDatetime
    domain: Domain
    metric: str
    value: float
    unit: str
    geography_scope: str = "Singapore"
    baseline_value: float | None = Field(default=None, ge=0)
    baseline_description: str | None = None
    source_id: str
    source_url: str
    source_confidence: float = Field(ge=0, le=1)
    summary: str
    limitations: str
    sensitivity: Literal["public"] = "public"


class SourceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    publisher: str
    title: str
    url: str
    domain: Domain
    status: SourceStatus
    retrieved_at: AwareDatetime
    observation_count: int = Field(ge=0)
    cadence: str
    note: str


class PublicDataBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieved_at: AwareDatetime
    geography_scope: str = "Singapore"
    observations: list[PublicObservation] = Field(default_factory=list)
    sources: list[SourceCoverage] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_provenance(self) -> PublicDataBundle:
        source_ids = [source.source_id for source in self.sources]
        observation_ids = [item.observation_id for item in self.observations]
        if len(source_ids) != len(set(source_ids)) or len(observation_ids) != len(set(observation_ids)):
            raise ValueError("Public source and observation identifiers must be unique")
        counts: dict[str, int] = {}
        for item in self.observations:
            if item.source_id not in source_ids:
                raise ValueError("Every public observation must have source coverage")
            counts[item.source_id] = counts.get(item.source_id, 0) + 1
        for source in self.sources:
            if source.observation_count != counts.get(source.source_id, 0):
                raise ValueError("Source coverage count must match its observations")
            if source.status in {SourceStatus.UNAVAILABLE, SourceStatus.CONTEXT_ONLY} and source.observation_count:
                raise ValueError("Unavailable or context-only sources cannot contain measurements")
        return self


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
    responsible_role: str | None = None


class ProposedAction(BaseModel):
    action_id: str
    title: str
    owner: str
    rationale: str
    consequence: str
    status: ActionStatus = ActionStatus.PENDING
    evidence_ids: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    completion_criterion: str | None = None
    review_trigger: str | None = None
    task_status: TaskStatus = TaskStatus.UNASSIGNED
    due_at: AwareDatetime | None = None
    assigned_at: AwareDatetime | None = None
    acknowledged_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    result: str | None = None


class ActionEvent(BaseModel):
    """Local, self-reported history; this is not an authenticated agency audit."""

    action_id: str
    event: Literal["approved", "rejected", "assigned", "acknowledged", "completed"]
    actor: str = Field(min_length=1)
    recorded_at: AwareDatetime
    note: str


class EventNode(BaseModel):
    signal_id: str
    timestamp: AwareDatetime
    domain: Domain
    location_cell: str
    source_id: str
    provenance: str
    anomalous: bool
    contextual: bool


class EventLink(BaseModel):
    signal_ids: tuple[str, str]
    gap_hours: float = Field(ge=0)
    relationship: Literal["co_occurrence", "contextual_association"]


class EventGraph(BaseModel):
    nodes: list[EventNode] = Field(default_factory=list)
    links: list[EventLink] = Field(default_factory=list)
    limitations: str = "No comparable signal-level observations were supplied; no event links are inferred."


class ImpactAssessment(BaseModel):
    severity: Literal["unassessed"] = "unassessed"
    affected_domains: list[Domain] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    summary: str = "Clinical severity, population exposure and service disruption have not been established."


class AgentFunction(BaseModel):
    role_id: str
    name: str
    tools: list[str]
    status: Literal["completed", "awaiting_human", "unavailable"]
    summary: str


class SpecialistReview(BaseModel):
    """A deterministic role review, not an independent model opinion."""

    role_id: str
    responsibility: str
    source_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class RunMetrics(BaseModel):
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    fallback_used: bool = False
    completed_within_limits: bool = True
    assessment_duration_ms: int = Field(default=0, ge=0)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    title: str
    description: str
    data_notice: str
    initial_signals: list[Signal] = Field(min_length=1)
    new_evidence_signals: list[Signal] = Field(default_factory=list)
    expected_leading_hypothesis: Hypothesis
    expected_status: CaseStatus

    @model_validator(mode="after")
    def require_unique_signals(self) -> Scenario:
        signal_ids = [signal.signal_id for signal in self.initial_signals + self.new_evidence_signals]
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("Signal identifiers must be unique across both evidence packets")
        return self


class CaseState(BaseModel):
    case_id: str
    scenario_id: str
    scenario_title: str
    signals: list[Signal]
    is_public: bool = False
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
    specialist_reviews: list[SpecialistReview] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    event_graph: EventGraph = Field(default_factory=EventGraph)
    primary_verification_id: str | None = None


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
    specialist_reviews: list[SpecialistReview] = Field(default_factory=list)
    sensitivity: Literal["synthetic", "public"] = "synthetic"
    event_graph: EventGraph = Field(default_factory=EventGraph)
    impact: ImpactAssessment = Field(default_factory=ImpactAssessment)
    agent_functions: list[AgentFunction] = Field(default_factory=list)
    primary_verification_id: str | None = None
    executive_brief: str = ""
    action_history: list[ActionEvent] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)
    previous_assessments: list[RiskProfile] = Field(default_factory=list)
    input_signal_ids: list[str] = Field(default_factory=list)
    input_fingerprint: str = ""
