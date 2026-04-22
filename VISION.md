# mcp-k8s-utility — Vision

**Tagline:** Unavoidable Kubernetes toil, handled in plain English.

## Why this exists

Projects 01–04 each solve a slice of production MCP for Kubernetes:

| # | Project | What it proves |
|---|---|---|
| 04 | mcp-prod-readiness | Policy-as-code readiness checks, golden fixtures, kind-isolated CI |
| 03 | mcp-deploy-intel | LLM-backed structured deploy reasoning with guarded context |
| 02 | mcp-observatory | Fleet-wide Prometheus-driven observability + SDK instrumentation |
| 01 | mcp-k8s-secure-ops | OPA + Kyverno + short-lived tokens for auditable write actions |

Project 00 is the **capstone**: it takes the architectural primitives proven in 01–04 (guarded context, typed tools, OPA gates, short-lived tokens, telemetry SDK, trusted-publisher release pipeline) and aims them at the *unavoidable toil* that burns hours of every platform team's week.

An organization adopting this gets immediate, visible value: hours back per engineer per week, fewer pages, shorter MTTR on toil incidents, auditable records of every remediation.

## Target personas

- **Platform engineer on-call** — "a node is NotReady at 2am, what now?"
- **SRE lead** — "I need an audit trail of every PDB override last quarter."
- **Dev asking for a bump** — "my pod is OOMKilling; what limits should I set?"
- **Security engineer** — "which certificates expire in the next 14 days across all clusters?"

## Scope — the toil we target

These are *unavoidable* in production, poorly automated at most orgs, and each costs hours of engineer time per incident:

1. **Certificate lifecycle** — expiry scanning, renewal triggers via cert-manager, post-renewal pod rollout, cluster-CA rotation assistance.
2. **Node lifecycle** — patching drain/uncordon workflows, kernel-update windows, reboot scheduling honoring PDBs.
3. **Resource right-sizing** — VPA/Goldilocks-style recommendations derived from Prometheus history, per-namespace cost attribution, "what should this pod's limits be?"
4. **PDB management** — find disruptive PDBs (maxUnavailable=0, minAvailable=100%), suggest safe values, simulate eviction under proposed PDB.
5. **Eviction and pressure handling** — diagnose why evictions happen, recommend PriorityClass changes, surface disk/memory pressure sources.
6. **Disk and log hygiene** — node `/var/log` growth, container log rotation settings, PVC fill-rate projections, orphaned PVs.
7. **Image and secret hygiene** — unused imagePullSecrets, stale image tags on nodes, orphaned ServiceAccount tokens.
8. **Pipeline-replaceable toil** — one-shot remediations that today live as cron jobs or CI pipelines ("clean up evicted pods", "restart deployments with expired mounted secrets").

Every tool answers in natural language *and* returns structured output an automation can act on — so it is usable by a human in Claude Desktop **and** by a scheduled agent.

## Non-goals

- Replacing a full GitOps or policy platform (Argo, Flux, Kyverno at org scale).
- Becoming a full observability stack — we *consume* Prometheus, we do not host it.
- Write actions without the secure-ops guardrails. Every write tool here composes with project 01's OPA + Kyverno + TokenRequest stack.

## Architectural reuse

| From project | Reused here |
|---|---|
| 04 prod-readiness | Check-pattern (`CheckSpec → CheckResult`), kind-based golden tests |
| 03 deploy-intel | `DeployContext.guard(needs=...)` pattern, litellm+instructor typed LLM |
| 02 observatory | `observatory-sdk` auto-instrumentation, fleet-wide Prometheus queries |
| 01 secure-ops | OPA pre-flight, Kyverno admission, TokenRequest-minted per-action SAs |

Project 00 adds no new core primitives — it is a portfolio of *tools* layered on the primitives the other four already ship.

## Release shape

- Python 3.11, `uv`, FastMCP 3.x, typer CLI — same stack as 01–04.
- Co-versioned with project 01 so `mcp-k8s-utility` depends on `mcp-k8s-secure-ops` for any write action.
- Helm chart, cosign-signed GHCR image, SBOM, PyPI trusted publisher — same release pipeline.
- Phased plans: **v0.1 diagnostic (read-only)**, **v0.5 recommendations (read + LLM)**, **v1.0 remediations (writes via secure-ops broker)**.

## Success criteria for v1.0

- ≥ 12 tools across the 8 toil categories.
- Every write tool routes through secure-ops broker; no tool holds its own cluster-admin credentials.
- One full demo scenario per toil category, runnable in a kind cluster in under 60 seconds.
- Published to PyPI, GHCR, with Helm chart, under the same trusted-publisher + cosign regime as 01–04.
- A clear "cost-saved" claim on the README backed by reproducible timings on the demo scenarios.
