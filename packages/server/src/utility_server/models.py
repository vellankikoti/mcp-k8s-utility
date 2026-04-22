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
