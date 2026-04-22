# mcp-k8s-utility — Roadmap

This is a high-level phased roadmap. Each phase will get its own spec + plan under `docs/superpowers/` once project 01 ships and we formally brainstorm Project 0.

## Sequencing

Project 0 starts **after** project 01 (secure-ops) reaches v1.0.0. It depends on the secure-ops broker for every write action, so secure-ops must be stable first.

```
04 (shipped) → 03 (shipped) → 02 (shipped) → 01 (next) → 00 (capstone)
```

## Phased plans

### Phase 0.1 — Diagnostic surface (read-only)

Ship the complete read-only diagnostic surface so the value is provable before any write primitive exists.

Tools (indicative):
- `list_expiring_certificates(days: int)` — scan Secrets of type `kubernetes.io/tls` + cert-manager Certificates.
- `find_disruptive_pdbs()` — PDBs that block drain.
- `recommend_resources(workload, window)` — VPA-style, from Prometheus history.
- `project_pvc_fill(window)` — linear + trend projection.
- `find_orphaned_resources()` — SA tokens, PVCs, imagePullSecrets.
- `diagnose_evictions(namespace, window)` — correlate events + pressure metrics.
- `node_log_volume_report()` — `/var/log` growth per node.

Release: **v0.1.0** — PyPI + GHCR + Helm, read-only.

### Phase 0.5 — Recommendations (LLM-backed)

Typed structured recommendations via litellm+instructor. Every recommendation carries a deterministic fallback so it works with `--no-llm`.

Tools (indicative):
- `recommend_pdb(workload)` — safe `maxUnavailable` given replica count + rollout velocity.
- `recommend_node_drain_plan(node)` — ordered drain sequence honoring PDBs.
- `recommend_cert_rotation_window(cert)` — based on workload traffic patterns.
- `explain_eviction(pod)` — human-readable root cause + remediation.

Release: **v0.5.0**.

### Phase 1.0 — Remediations (writes via secure-ops)

Every write tool here is a thin client of the secure-ops broker. OPA policy + Kyverno admission + TokenRequest-minted per-action SA. No exceptions.

Tools (indicative):
- `renew_certificate(cert)` — triggers cert-manager renewal + rollout of mounting workloads.
- `drain_node(node, plan)` — executes a plan produced by `recommend_node_drain_plan`.
- `apply_resource_recommendation(workload)` — patches limits/requests.
- `cleanup_evicted_pods(namespace)` — replaces the classic cron.
- `rotate_service_account_tokens(sa)`.
- `schedule_node_reboot(node, window)` — honors PDBs, respects maintenance windows.

Release: **v1.0.0** — full remediation surface, cosign-signed, SBOM, trusted publisher.

## Risks & mitigations

- **Scope creep** — the toil list is unbounded; we hold the line at the 8 categories in VISION.md for v1.0.
- **Write safety** — enforced by reuse of secure-ops broker. Project 0 owns *no* cluster-admin credentials directly.
- **LLM determinism** — every recommendation has a deterministic fallback path, per the deploy-intel pattern.
- **Demo fragility** — toil scenarios tend to be environment-specific; we pre-seed kind clusters with reproducible toil fixtures (expired cert, filled PVC, wedged PDB, etc.).

## Open questions (to resolve at brainstorm time)

- Does Project 0 depend on `mcp-observatory-sdk` for its own self-instrumentation? (Likely yes.)
- Do we ship a `utility-agent` daemon that runs scheduled toil reports, or stay stateless like 01–04?
- Helm umbrella chart that installs 00 + 01 together, or keep them independently installable?
