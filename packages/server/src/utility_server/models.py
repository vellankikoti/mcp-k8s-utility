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
