# Changelog

## v0.4.0 — 2026-04-23

**Control-plane certificate rotation + two correctness fixes from end-to-end validation.**

### Added
- **Tool #7 `check_control_plane_cert_expiry`** — probes every master node via a short-lived read-only privileged Pod that chroots into the host and runs `openssl x509 -enddate`. Returns per-node expiries for `apiserver`, `apiserver-kubelet-client`, `front-proxy-client`, and `etcd/server` certs, plus the soonest-to-expire count in days.
- **Tool #8 `generate_control_plane_rotation_runbook`** — emits the exact 14-command kubeadm rotation sequence as Markdown, with pre-flight and verification sections. Pure read.
- **Tool #9 `execute_control_plane_rotation`** — runs the runbook on one master via a privileged Pod. Four safety gates: business-hours, cluster health (all masters Ready), etcd quorum intact, no concurrent rotation. Dry-run default. Best-effort rollback on step failure. Transient-exec retry absorbs the kubelet-cert-reload race after `kubeadm certs renew all`.
- **Tool #10 `build_vault_cert_bundle`** — post-rotation: reads `apiserver.crt` from each master, concatenates with per-node separator headers, base64-encodes. Emits the blob ready to paste into the Vault team's ticket for the External Secrets Operator pipeline.
- **3-control-plane demo bootstrap** (`tests/demo/demo-cp-up.sh`, `tests/demo/cp-rotation-kind.yaml`) — brings up a kind cluster with 3 control-planes + 1 worker for rotation rehearsals.

### Fixed (from e2e validation)
- `opensearch_retention_cleanup` retention-tag detection now also checks the index's mapping `_meta.retention` key. OpenSearch 2.x rejects unknown keys from the settings path, so mapping-metadata is the reliable spot. `OpenSearchClient.get_index_mapping` is a new thin method.
- `tune_alert_thresholds` flap detection switched from `changes(ALERTS{...})` to `count_over_time(ALERTS{...})`. `changes()` returns zero when a series goes absent between firings (common for alerts that resolve cleanly), which made chatty alerts invisible. `count_over_time` counts sample presence and catches them correctly.

### Invariants (unchanged)
- LLM never holds cluster credentials; LLM never decides a write.
- Every destructive path is dry-run-default, policy-gated, and rate-limited.
- Every control-plane write is audited and rolls back on failure.

### Published
- PyPI: `mcp-k8s-utility==0.4.0`.
- GHCR: `ghcr.io/vellankikoti/mcp-k8s-utility:v0.4.0` (multi-arch linux/amd64 + linux/arm64, cosign-signed).
- SBOM: `sbom-v0.4.0.cdx.json` attached to the GitHub Release.

### Validation
- 133 tests passing; ruff + mypy strict clean.
- End-to-end validated on a 3-control-plane kind cluster. Real rotation ran to `status=completed`: 14/14 steps rc=0 in 78 seconds, cert dates advanced ~1 year on the target master, cluster health preserved throughout, Vault bundle built with 3 distinct PEMs and verified round-trip.

## v0.3.0 — 2026-04-22

**Week 3 — full tool surface + Dockerfile + kind demo harness + cosign-signed multi-arch image.**

### Added
- **Tool #6 `draft_postmortem`** — synthesis tool over K8s events + Prometheus metrics + OpenSearch logs + secure-ops audit rows. Emits a Google-SRE-style markdown postmortem. Every source is gracefully optional; deterministic fallback always renders valid markdown when the LLM is disabled.
- **Dockerfile** — multi-stage Python 3.13-slim, non-root user, 117 MiB image, built and published to GHCR with cosign keyless signature and CycloneDX SBOM.
- **Makefile** — `make demo`, `make demo-down`, `make dashboard`, `make test`, `make gate` convenience targets.
- **kind demo harness** (`tests/demo/`) — `demo-up.sh` bootstraps a 1-node kind cluster, installs cert-manager and a lite Prometheus, seeds `demo-prod` + `demo-staging` namespaces with a self-signed expiring Certificate, an oversized `checkout` Deployment, and a stable `Failed/Evicted` Pod via the ghost-node technique.
- **Scenario cheat-sheets** — A (cert renewal), B (evicted-pod cleanup), C (postmortem drafting).
- **Docs** — `docs/quickstart.md` (3-command onboarding), `docs/claude-desktop-config.md` (MCP wiring + troubleshooting).

### Fixed
- `days_until_expiry` now uses ceiling rounding so a cert 47.6 h away shows as 2 days, not 1 — operators see accurate urgency.
- `make demo` bumped kind `--wait` from 120 s to 300 s; added a proactive WARN when other kind clusters are running (Docker Desktop memory pressure was causing kubeadm TLS timeouts on modestly provisioned machines).
- Evicted-pod seeding now uses the **ghost-node technique** (Pod bound to a nonexistent `nodeName`) so kubelet never reconciles the status patch. Scenario B now reliably shows 1 evicted pod across all recent k8s versions.

### Published
- PyPI: `mcp-k8s-utility==0.3.0` (all 13 tools).
- GHCR: `ghcr.io/vellankikoti/mcp-k8s-utility:v0.3.0` (multi-arch linux/amd64 + linux/arm64, cosign-signed).
- SBOM: attached to GitHub Release as `sbom-v0.3.0.cdx.json`.

### Invariants (unchanged — enforced in every tool)
- LLM narrates, never decides. Every `narrate()` call has a deterministic fallback. `UTILITY_LLM_PROVIDER=disabled` yields identical safety behavior.
- Every destructive write is dry-run by default, pattern/tag/allowlist-gated, and rate-limited.
- Policy-gated writes route through the `mcp-k8s-secure-ops` broker: OPA pre-flight + 5-min per-action token + tamper-evident audit.

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
