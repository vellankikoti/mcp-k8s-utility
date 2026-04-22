# Changelog

## v0.1.0 — 2026-04-22

**Alpha release — Week 1 of capstone development.**

First two tools + LLM-agnostic adapter shipped. Foundation for 4 more tools coming in Weeks 2-3.

### Added
- **`UtilityLLM` adapter** — single interface over 5 LLM providers (Vertex, Anthropic, OpenAI, Ollama, disabled). No provider is required; every call has a deterministic fallback. Switch providers with one env var.
- **`list_expiring_certificates`** — scans cert-manager `Certificate` resources across namespaces; filters by days-to-expiry.
- **`propose_certificate_renewal`** — builds a dry-run renewal plan with full dependent-workload analysis (Deployments mounting the cert's Secret via volume, envFrom, or env valueFrom).
- **`execute_certificate_renewal`** — applies the plan with three built-in safety gates: (a) dry-run by default, (b) refuses during UTC business hours unless `force_during_business_hours=True`, (c) every dependent rollout goes through the `mcp-k8s-secure-ops` broker (OPA-gated, 5-min per-action token, tamper-evident audit).
- **`propose_right_size_plan`** — Prometheus-driven CPU/memory recommendations for Deployments. Uses p99 + headroom (CPU 1.25×, memory 1.20×) with minimum floors. LLM narration if a provider is configured; deterministic statistical summary otherwise. Read-only by design — no apply path in v0.1.

### Safety invariants
- LLM never holds cluster credentials.
- Every write passes through the secure-ops broker (OPA policy + short-lived token).
- Every tool call is audit-chained via the upstream secure-ops ledger.
- `narrate()` never raises — returns `None` on any provider failure so the caller's deterministic fallback activates.

### Infrastructure
- Depends on `mcp-k8s-secure-ops==1.0.3` (published).
- Multi-arch GHCR image via release workflow (Dockerfile follows in Week 2).
- Release pipeline publishes to PyPI (trusted publisher via GitHub Environment `pypi`).
- 44 tests passing on Python 3.11, ruff + mypy strict clean.

### Known gaps (v0.1.0)
- No Dockerfile yet — image job will fail until one lands in Week 2.
- No kind-cluster demo harness — follows in Week 2.
- Tools 3-6 (cleanup_evicted_pods, tune_alert_thresholds, opensearch_retention_cleanup, draft_postmortem) land in Weeks 2-3.
- No dashboard — Week 2.
