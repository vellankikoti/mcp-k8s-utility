# Changelog

## v0.2.0 — 2026-04-22

**Week 2 alpha — 5 tools + dashboard + LLM-agnostic narration everywhere.**

### Added
- **Tool #3 `cleanup_evicted_pods`** — scan/plan/execute with phase-filter, age gate, per-namespace rate limit, and env-driven namespace allowlist. Only touches pods already in `Failed/Evicted`; never touches live workloads.
- **Tool #4 `tune_alert_thresholds`** — Prometheus-driven flappy-alert detection with advisory `for:` duration recommendations. Critical-severity alerts flagged for human review; no apply path (Grafana PATCH deferred to v0.3).
- **Tool #5 `opensearch_retention_cleanup`** — index-pattern gate, retention-tag safety, dry-run default, per-call rate limit. Shipped a minimal `OpenSearchClient` HTTP wrapper that never raises.
- **Dashboard** (`mcp-k8s-utility dashboard`) — FastAPI + HTMX on `:8080`. Five live tiles + a demo-runner: system health, LLM provider, tool activity, OPA decisions, per-action ServiceAccounts, plus three safe read-only demo buttons. Graceful degradation: every tile renders correctly when its backing system is missing.

### Invariants reinforced
- Every write tool has a denial scenario exercised by unit tests.
- Every LLM call has a deterministic fallback; `--no-llm` gives identical safety behavior.
- OpenSearch delete path is pattern-gated (deny-by-default) and compliance-tag-safe.

### Infrastructure
- 88 tests passing, ruff + mypy strict clean.
- PyPI: `mcp-k8s-utility==0.2.0`.
- MCP registry: 12 tools visible via `list_tools()`.

### Known gaps (v0.2.0)
- No Dockerfile yet (release `image` job disabled until Week 3).
- No kind-cluster demo harness yet (Week 3).
- `draft_postmortem` tool #6 deferred to Week 3.
- Grafana alert-rule apply path deferred to v0.3.

## v0.1.1 — 2026-04-22

Post-v0.1.0 verification sweep found 2 demo-visible polish bugs + 1 UX gap. All fixed.

### Fixed
- **MCP `serverInfo.version`** now reports the package version (`0.1.1`) instead of the FastMCP library version. Claude Desktop and other MCP hosts will display the correct product version.
- **`llm-probe`** on invalid `UTILITY_LLM_PROVIDER` now prints a one-line error and exits 1 cleanly — no raw traceback leaked to users.

### Docs
- README now states Python 3.11+ requirement explicitly (macOS `python3` resolves to 3.9 and was silently failing `pip install`).

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
