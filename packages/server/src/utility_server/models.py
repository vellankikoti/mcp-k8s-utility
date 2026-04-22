from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class K8sObjectRef(BaseModel):
    kind: str
    api_version: str
    namespace: str
    name: str
    uid: str | None = None


class CertificateSummary(BaseModel):
    ref: K8sObjectRef
    secret_name: str
    dns_names: list[str]
    not_after: datetime
    days_until_expiry: int
    issuer: str | None = None
    is_ready: bool


class AffectedWorkload(BaseModel):
    ref: K8sObjectRef
    mount_reason: Literal["secret_volume", "env_secret_ref", "imagepullsecret"]


class RenewalStep(BaseModel):
    certificate: K8sObjectRef
    annotation_patch: dict[str, Any]
    dependent_rollouts: list[K8sObjectRef]


class RenewalPlan(BaseModel):
    window_days: int
    steps: list[RenewalStep]
    force_during_business_hours: bool
    proposed_at: datetime


class RenewalStepResult(BaseModel):
    certificate: K8sObjectRef
    status: Literal["annotated", "skipped_business_hours", "skipped_dry_run", "failed"]
    rollouts_triggered: list[K8sObjectRef]
    error: str | None = None


class RenewalResult(BaseModel):
    dry_run: bool
    executed_at: datetime
    steps: list[RenewalStepResult]
    refused: bool = False
    refusal_reason: str | None = None


class ResourceQuantities(BaseModel):
    cpu_cores: float  # e.g. 0.125 for 125m
    memory_mib: float  # e.g. 256.0 for 256Mi


class WorkloadResources(BaseModel):
    requests: ResourceQuantities
    limits: ResourceQuantities | None = None


class ResourceRecommendation(BaseModel):
    ref: K8sObjectRef
    container: str
    current: WorkloadResources
    observed_p95: ResourceQuantities
    observed_p99: ResourceQuantities
    recommended: WorkloadResources
    rationale: str
    savings_estimate_cpu_cores: float  # positive = would save
    savings_estimate_memory_mib: float


class RightSizePlan(BaseModel):
    namespace: str | None
    window_days: int
    recommendations: list[ResourceRecommendation]
    narration: str | None  # optional LLM summary
    proposed_at: datetime


class EvictedPodSummary(BaseModel):
    ref: K8sObjectRef
    eviction_reason: str  # typically "Evicted"; could be "NodeLost", etc.
    eviction_message: str
    evicted_at: datetime | None
    age_hours: float | None  # None if evicted_at is None
    node_name: str | None
    owner_kind: str | None  # Deployment, StatefulSet, Job — or None
    owner_name: str | None


class CleanupCandidate(BaseModel):
    pod: EvictedPodSummary
    will_delete: bool  # subject to allowlist / age / rate-limit gates
    skip_reason: str | None = None  # populated when will_delete=False


class CleanupPlan(BaseModel):
    namespace: str | None
    min_age_hours: float
    max_deletes_per_namespace: int
    namespace_allowlist: list[str]
    candidates: list[CleanupCandidate]
    proposed_at: datetime


class CleanupOutcome(BaseModel):
    pod: K8sObjectRef
    status: Literal["deleted", "skipped_dry_run", "skipped_policy", "failed"]
    error: str | None = None


class CleanupResult(BaseModel):
    dry_run: bool
    executed_at: datetime
    outcomes: list[CleanupOutcome]
    deleted_count: int
    skipped_count: int
    failed_count: int


class NoisyAlert(BaseModel):
    alertname: str
    severity: str | None
    namespace: str | None
    fires_count: int  # transitions firing→resolved→firing
    window_hours: float
    flaps_per_hour: float
    labels: dict[str, str]


class AlertTuningProposal(BaseModel):
    alert: NoisyAlert
    current_for: str | None  # e.g. "5m" — None if not known
    recommended_for: str  # e.g. "15m"
    rationale: str
    requires_human_review: bool  # True when severity=critical
    fallback_only: bool  # True when LLM provider returned None


class AlertTuningReport(BaseModel):
    window_hours: float
    min_flaps_per_hour: float
    findings: list[AlertTuningProposal]
    narration: str | None
    analyzed_at: datetime


class OpenSearchIndexSummary(BaseModel):
    name: str
    doc_count: int
    size_bytes: int
    creation_timestamp: datetime | None
    age_days: float | None
    retention_tagged: bool
    matched_pattern: str | None


class RetentionCleanupCandidate(BaseModel):
    index: OpenSearchIndexSummary
    will_delete: bool
    skip_reason: str | None = None


class RetentionCleanupPlan(BaseModel):
    older_than_days: float
    index_patterns: list[str]
    max_deletes: int
    candidates: list[RetentionCleanupCandidate]
    total_bytes_to_reclaim: int
    total_docs_to_remove: int
    narration: str | None
    proposed_at: datetime


class RetentionCleanupOutcome(BaseModel):
    index: str
    status: Literal["deleted", "skipped_dry_run", "skipped_policy", "failed"]
    size_bytes: int
    error: str | None = None


class RetentionCleanupResult(BaseModel):
    dry_run: bool
    executed_at: datetime
    outcomes: list[RetentionCleanupOutcome]
    deleted_count: int
    deleted_bytes: int
    skipped_count: int
    failed_count: int
