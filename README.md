# mcp-k8s-utility

**An AI assistant for the boring parts of running Kubernetes — with safety rails so it can't break things.**

- [PyPI](https://pypi.org/project/mcp-k8s-utility/) · [GHCR](https://ghcr.io/vellankikoti/mcp-k8s-utility)
- v0.5.0 — 2026-04-23

## What is this?

Running a Kubernetes cluster involves a long list of repetitive chores. Renewing
certificates before they expire. Cleaning up pods that got evicted during disk
pressure. Tuning alerts that fire every 10 minutes for no real reason. Rotating
the cluster's own CA certificates once a year. Writing postmortems after
incidents.

These tasks all have something in common:

- Nobody wants to do them.
- If you skip them, things eventually break.
- If you rush them, things break faster.

This tool takes those jobs and lets you do them by **asking an AI in plain English**.
But the AI doesn't get your cluster password. It can't decide anything risky.
Everything dangerous is gated by policies you define, not by the AI's mood. And
if you don't want to use an AI at all, every tool still works — just without the
friendly narration.

## What can it actually do?

17 tools, grouped into 7 jobs:

| Job | Tools | What changes for you |
|---|---|---|
| **Keep TLS certificates fresh** | 1–3 | The AI tells you which certs expire soon, plans the renewal, and does it — refusing if it's the middle of a workday unless you explicitly approve. |
| **Make pods the right size** | 4 | Looks at 7 days of real CPU/memory usage. Tells you which pods are 5× bigger than they need to be, and which might OOM. |
| **Clean up leftover junk** | 5–7 | Finds evicted/failed pods nobody deleted. Shows you the list. Deletes the safe ones after you confirm. |
| **Stop alert fatigue** | 8–9 | Finds alerts that fire and resolve constantly. Suggests better thresholds. Critical alerts are flagged for human review — not auto-tuned. |
| **Manage log storage** | 10–12 | Finds old OpenSearch indices. Shows how much disk they're wasting. Deletes ones not marked for compliance retention. |
| **Write postmortems in 30 seconds** | 13 | Pulls the last 30 minutes of events, metrics, logs, and audit rows. Drafts a proper Google-SRE postmortem. You edit it; you don't start from blank. |
| **Rotate cluster CA certificates** | 14–17 | For kubeadm clusters: the one-year rotation nobody wants to touch. Checks every master, runs the 14-step runbook with safety gates, rolls back if anything fails, builds the cert bundle for your Vault team. |

## Why should I trust an AI with my cluster?

Four rules the AI physically cannot break:

1. **The AI doesn't have your cluster password.** It calls a tool. The tool calls Kubernetes.
2. **The AI doesn't decide anything risky.** Policies you wrote decide. The AI can explain the decision.
3. **Every action is logged in a way nobody can edit** — each row is cryptographically linked to the previous one. If someone tampers, the chain breaks and you see it.
4. **If the AI is off, everything still works.** Every AI call has a deterministic fallback. You can run the whole toolkit with zero AI and get the same safety.

## Who is this for?

- **Platform engineers / SREs** — the day-to-day operators who want Saturdays back.
- **Security engineers** — who need an audit trail and can't approve tools that hand AI the root password.
- **Engineering leaders** — who want AI-assisted ops without becoming the next "AI deleted production" headline.

You don't need to change your stack. It uses the Kubernetes you already have, your
existing Prometheus, cert-manager, OpenSearch, whatever.

## How do I try it?

Three commands on a laptop:

```bash
pip install 'mcp-k8s-utility==0.5.0'
mcp-k8s-utility version
# then follow the k3d quickstart below
```

Or connect it to Claude Desktop and ask:

> "List certs expiring in the next 14 days in my cluster and propose a safe renewal plan."

The AI will call the tools. The tools will do the work safely. You'll get a reply
with the answer and the evidence.

## What it will NOT do

Being honest up front:

- **It will not rotate certificates on managed Kubernetes** (EKS, GKE, AKS). The cloud
  provider owns those certs — it's their job. The tool detects this and tells you.
- **It will not touch workloads you haven't allowed** — every delete path checks a
  pattern allowlist; no pattern, no delete.
- **It will not replace your change management.** For risky actions, it refuses during
  business hours by default. Your on-call is still on-call.
- **It will not work on unusual Kubernetes setups** (Talos, Bottlerocket, certain
  hardened OpenShift profiles) — those haven't been tested and the privileged-Pod
  technique may be blocked.

---

<!-- END OF SIMPLIFIED INTRO — deep workbook continues below -->

## Status and validation

**13 workload tools work on any Kubernetes** (k3d, kind, EKS, GKE, AKS, kubeadm).
The 4 control-plane rotation tools (#14–17) **require kubeadm** and will return a
structured refusal (no Pods created) on k3s/k3d or cloud-managed clusters — see
[Per-tool workbook](#per-tool-workbook).

## Table of contents

- [What's actually validated](#whats-actually-validated)
- [Quick install](#quick-install)
- [Quickstart on a 3-node k3d cluster](#quickstart-on-a-3-node-k3d-cluster)
- [Per-tool workbook](#per-tool-workbook)
  - [Tool 1 — list_expiring_certificates](#tool-1--list_expiring_certificates)
  - [Tool 2 — propose_certificate_renewal](#tool-2--propose_certificate_renewal)
  - [Tool 3 — execute_certificate_renewal](#tool-3--execute_certificate_renewal)
  - [Tool 4 — propose_right_size_plan](#tool-4--propose_right_size_plan)
  - [Tool 5 — list_evicted_pods](#tool-5--list_evicted_pods)
  - [Tool 6 — propose_cleanup_plan](#tool-6--propose_cleanup_plan)
  - [Tool 7 — execute_cleanup_plan](#tool-7--execute_cleanup_plan)
  - [Tool 8 — list_noisy_alerts](#tool-8--list_noisy_alerts)
  - [Tool 9 — propose_alert_tuning](#tool-9--propose_alert_tuning)
  - [Tool 10 — list_old_opensearch_indices](#tool-10--list_old_opensearch_indices)
  - [Tool 11 — propose_retention_cleanup](#tool-11--propose_retention_cleanup)
  - [Tool 12 — execute_retention_cleanup](#tool-12--execute_retention_cleanup)
  - [Tool 13 — draft_postmortem](#tool-13--draft_postmortem)
  - [Tool 14 — check_control_plane_cert_expiry](#tool-14--check_control_plane_cert_expiry)
  - [Tool 15 — generate_control_plane_rotation_runbook](#tool-15--generate_control_plane_rotation_runbook)
  - [Tool 16 — execute_control_plane_rotation](#tool-16--execute_control_plane_rotation)
  - [Tool 17 — build_vault_cert_bundle](#tool-17--build_vault_cert_bundle)
- [LLM provider setup](#llm-provider-setup)
- [RBAC / production install](#rbac--production-install)
- [Environment variables reference](#environment-variables-reference)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)

---

## What's actually validated

| Tool | k3d/k3s | kubeadm kind | EKS/GKE/AKS | Notes |
|---|---|---|---|---|
| list_expiring_certificates | yes (needs cert-manager) | yes | yes | |
| propose_certificate_renewal | yes | yes | yes | |
| execute_certificate_renewal | yes | yes | yes | needs secure-ops broker |
| propose_right_size_plan | yes (needs Prometheus) | yes | yes | |
| list_evicted_pods | yes | yes | yes | |
| propose_cleanup_plan | yes | yes | yes | |
| execute_cleanup_plan | yes | yes | yes | |
| list_noisy_alerts | yes (needs Prometheus) | yes | yes | |
| propose_alert_tuning | yes (needs Prometheus) | yes | yes | |
| list_old_opensearch_indices | yes (needs OpenSearch) | yes | yes | |
| propose_retention_cleanup | yes (needs OpenSearch) | yes | yes | |
| execute_retention_cleanup | yes (needs OpenSearch) | yes | yes | |
| draft_postmortem | yes | yes | yes | Prometheus/OpenSearch optional |
| check_control_plane_cert_expiry | **refused** | yes | **refused** | kubeadm only |
| generate_control_plane_rotation_runbook | **refused** | yes | **refused** | kubeadm only |
| execute_control_plane_rotation | **refused** | yes | **refused** | kubeadm only |
| build_vault_cert_bundle | **refused** | yes | **refused** | kubeadm only |

"Refused" means the tool returns `status="refused_unsupported_cluster_type"` with an
explanation — no Pods are created and nothing is mutated.

---

## Quick install

```bash
# Run once without installing
uvx --python 3.11 mcp-k8s-utility version

# Install into a venv
python3.11 -m venv .venv && source .venv/bin/activate
pip install 'mcp-k8s-utility==0.5.0'
mcp-k8s-utility version
# mcp-k8s-utility 0.5.0

# Pull the container image
docker pull ghcr.io/vellankikoti/mcp-k8s-utility:v0.5.0
```

---

## Quickstart on a 3-node k3d cluster

### 1. Prerequisites

Exact versions tested. Newer patch versions should work.

| Tool | Tested version | Install |
|---|---|---|
| k3d | 5.6.x | `brew install k3d` |
| kubectl | 1.30.x | `brew install kubectl` |
| Helm | 3.15.x | `brew install helm` |
| Python | 3.11+ | `brew install python@3.11` |

### 2. Bring up the cluster

```bash
k3d cluster create utility-demo \
  --servers 1 \
  --agents 2 \
  --port "9090:9090@loadbalancer" \
  --wait

kubectl config use-context k3d-utility-demo
kubectl get nodes
```

Expected output (names will differ):

```
NAME                        STATUS   ROLES                  AGE   VERSION
k3d-utility-demo-agent-0    Ready    <none>                 30s   v1.29.x
k3d-utility-demo-agent-1    Ready    <none>                 30s   v1.29.x
k3d-utility-demo-server-0   Ready    control-plane,master   45s   v1.29.x
```

### 3. Install cert-manager

```bash
helm repo add jetstack https://charts.jetstack.io --force-update
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set crds.enabled=true \
  --wait
```

Create a self-signed ClusterIssuer and a test Certificate that expires in 1 day
(short TTL so list_expiring_certificates picks it up immediately):

```bash
kubectl apply -f - <<'YAML'
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned
spec:
  selfSigned: {}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: demo-tls
  namespace: default
spec:
  secretName: demo-tls-secret
  issuerRef:
    name: selfsigned
    kind: ClusterIssuer
  duration: 24h
  renewBefore: 23h
  dnsNames:
    - demo.example.com
YAML
kubectl wait --for=condition=Ready certificate/demo-tls -n default --timeout=60s
```

### 4. Install Prometheus (kube-prometheus-stack, stripped down)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
helm install kube-prom prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --set grafana.enabled=false \
  --set alertmanager.enabled=false \
  --set prometheus.service.type=NodePort \
  --wait --timeout=5m
```

Get the Prometheus URL (NodePort varies):

```bash
PROM_PORT=$(kubectl -n monitoring get svc kube-prom-kube-prometheus-prometheus \
  -o jsonpath='{.spec.ports[0].nodePort}')
PROM_NODE=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[0].address}')
echo "http://${PROM_NODE}:${PROM_PORT}"
# Export for mcp-k8s-utility:
export PROMETHEUS_URL="http://${PROM_NODE}:${PROM_PORT}"
```

Verify:

```bash
curl -s "${PROMETHEUS_URL}/api/v1/query?query=up" | python3 -m json.tool | head -20
```

### 5. Seed evicted pods

The ghost-node technique produces a stable evicted-looking pod without needing
real disk pressure:

```bash
kubectl create ns demo-staging 2>/dev/null || true
kubectl -n demo-staging apply -f - <<'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: stale-pod-1
  labels: { demo: evicted-seed }
spec:
  nodeName: ghost-node-never-exists
  restartPolicy: Never
  containers:
    - name: ghost
      image: busybox:1.36
      command: ["sh", "-c", "sleep 1"]
YAML

# Patch the status to Evicted (requires --subresource=status)
kubectl -n demo-staging patch pod stale-pod-1 --type=merge --subresource=status -p \
  '{"status":{"phase":"Failed","reason":"Evicted","message":"disk pressure seeded for demo"}}'
```

### 6. Install mcp-k8s-utility

```bash
pip install 'mcp-k8s-utility==0.5.0'
mcp-k8s-utility version
```

### 7. Wire it into Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-k8s-utility": {
      "command": "mcp-k8s-utility",
      "args": ["serve-mcp"],
      "env": {
        "KUBECONFIG": "/Users/YOUR_USER/.kube/config",
        "PROMETHEUS_URL": "http://PROM_NODE:PROM_PORT"
      }
    }
  }
}
```

Restart Claude Desktop. You should see a hammer icon and "17 tools available" in
the Claude context panel.

### 8. Walk through each tool

Recommended order: start read-only, end with execute.

1. `list_expiring_certificates` — verifies cert-manager wiring
2. `list_evicted_pods` — verifies k8s access
3. `propose_right_size_plan` — verifies Prometheus access
4. `list_noisy_alerts` — verifies Prometheus alert data
5. `propose_cleanup_plan` — verifies evicted-pod detection
6. `propose_certificate_renewal` — verifies dependent-workload scan
7. `draft_postmortem` — synthesis across all sources
8. `execute_cleanup_plan` (dry_run=true first, then false)
9. `execute_certificate_renewal` (dry_run=true first)
10. CP-rotation tools — skip on k3d; they return structured refusal

---

## Per-tool workbook

### Tool 1 — `list_expiring_certificates`

**What it does:** Scans cert-manager `Certificate` resources cluster-wide or in a
namespace and returns those expiring within `within_days` days.

**Why this matters:** cert-manager auto-renews certificates, but the renewal can fail
silently — wrong issuer config, webhook misconfiguration, rate-limit hit. Ops teams
find out when TLS handshakes start failing in prod, not before. This tool surfaces
the impending expiry before it becomes an incident.

**How to test it:**

After step 3 above (short-lived cert seeded):

```bash
# Via Claude: "List certificates expiring within 30 days"
# Or directly with mcp-k8s-utility inspect:
```

Expected JSON shape:

```json
[
  {
    "ref": {"kind": "Certificate", "name": "demo-tls", "namespace": "default"},
    "secret_name": "demo-tls-secret",
    "dns_names": ["demo.example.com"],
    "days_until_expiry": 1,
    "is_ready": true
  }
]
```

**Where it saves time:** Daily cert-expiry check in a cluster with 30+ certs takes
~30 seconds via this tool vs. writing a loop over `kubectl get certificates -A`.

**Known limits:**

- Only reads cert-manager `Certificate` CRDs. Does not scan raw Kubernetes Secrets for
  manually created TLS certs, Ingress TLS, or Istio service mesh certs.
- Requires cert-manager CRDs installed. Returns empty list if they're absent.

---

### Tool 2 — `propose_certificate_renewal`

**What it does:** Builds a renewal plan for expiring certificates. For each cert it
scans for dependent Deployments that mount the cert's Secret via volume, envFrom, or
env valueFrom. Returns the plan as a structured object — no writes.

**Why this matters:** Forcing cert renewal via the annotation is a two-step operation:
annotate the cert, then roll the Deployments that loaded the old cert into memory.
This tool finds the Deployments automatically so the operator doesn't miss a service
that cached the old TLS material.

**How to test it:**

Ask Claude: "Propose a renewal plan for certificates expiring within 30 days."

Expected:

```json
{
  "window_days": 30,
  "steps": [
    {
      "certificate": {"name": "demo-tls", "namespace": "default"},
      "annotation_patch": {"metadata": {"annotations": {"cert-manager.io/force-renew-at": "..."}}},
      "dependent_rollouts": []
    }
  ]
}
```

`dependent_rollouts` is empty here because no Deployment mounts `demo-tls-secret`.
In production you'd see Deployments listed here.

**Known limits:**

- Scans Deployments only. StatefulSets, DaemonSets, and Jobs are not scanned for
  dependent-workload analysis (they are listed by other tools but not correlated
  with cert secrets here).
- The annotation-only approach works with cert-manager 1.13+. Older cert-manager
  uses `kubectl cert-manager renew`.

---

### Tool 3 — `execute_certificate_renewal`

**What it does:** Applies the renewal plan from tool 2. Patches the
`cert-manager.io/force-renew-at` annotation on each certificate. Rolls dependent
Deployments via the `mcp-k8s-secure-ops` broker (OPA-gated, short-lived token,
audit-chained). Dry-run by default.

**Why this matters:** Removing the human step of "patch the annotation, then remember
to restart the three Deployments that use it" eliminates the class of incidents where
the cert renewed but the service kept serving the old cert from memory.

**How to test it:**

```bash
# Dry run first (always)
# Ask Claude: "Execute the renewal plan in dry_run mode"
# Expected: each step shows status="skipped_dry_run"

# Real run
# Ask Claude: "Execute the renewal plan with dry_run=false"
# Outside business hours (UTC 13:00-21:00 Mon-Fri) OR with force=true
```

**Safety gates (in order):**

1. `dry_run=True` → no writes, returns skipped steps
2. Business-hours block (13:00-21:00 UTC Mon-Fri) → returns `refused=true`
3. Per-step: OPA policy check via secure-ops broker

**Known limits:**

- Business-hours window is configurable via `UTILITY_BUSINESS_HOURS_START_UTC`,
  `UTILITY_BUSINESS_HOURS_END_UTC`, `UTILITY_BUSINESS_HOURS_DAYS` env vars.
- Requires `mcp-k8s-secure-ops` broker for dependent rollout step. Without it,
  dependent rollouts are skipped with an error note.

---

### Tool 4 — `propose_right_size_plan`

**What it does:** Queries Prometheus for CPU and memory p95/p99 usage over the past
N days for every Deployment in a namespace. Compares to current `requests` and
`limits`. Recommends new values at p99 + 25% CPU headroom + 20% memory headroom,
with minimum floors (10m CPU, 16 MiB memory). LLM narration if a provider is
configured; deterministic summary otherwise.

**Why this matters:** Over-provisioned workloads waste money. Under-provisioned
workloads get OOMKilled or throttled. This tool gives you p99-based numbers with
explicit headroom, not guesses.

**How to test it:**

With Prometheus running:

```bash
# Ask Claude: "Propose right-sizing for the monitoring namespace"
```

Expected shape:

```json
{
  "namespace": "monitoring",
  "window_days": 7,
  "recommendations": [
    {
      "ref": {"name": "prometheus-operator"},
      "container": "prometheus-operator",
      "current": {"requests": {"cpu_cores": 0.1, "memory_mib": 128.0}},
      "observed_p95": {"cpu_cores": 0.03, "memory_mib": 45.0},
      "recommended": {"requests": {"cpu_cores": 0.05, "memory_mib": 64.0}},
      "savings_estimate_cpu_cores": 0.05,
      "savings_estimate_memory_mib": 64.0
    }
  ]
}
```

**Known limits:**

- Requires Prometheus with `container_cpu_usage_seconds_total` and
  `container_memory_working_set_bytes` metrics (standard kube-prometheus-stack).
- Returns empty `recommendations` if Prometheus is unreachable or no workloads exist
  in the namespace.
- No apply path — this tool only reads and recommends. Applying changes requires
  `kubectl set resources` or editing the Deployment YAML. A future version will
  add an optional apply step.
- `window_days` defaults to 7. A freshly created workload with < 7 days of history
  will show p99=0 and recommend minimums.

---

### Tool 5 — `list_evicted_pods`

**What it does:** Lists pods in `Failed/Evicted` state. Uses Kubernetes field selector
`status.phase=Failed` server-side (not client-side filtering), then checks
`status.reason=Evicted` locally. Returns age, eviction message, and owner workload.
Read-only.

**Why this matters:** Kubelet leaves Evicted pods around after disk or memory pressure
events. They consume no CPU or memory but inflate `kubectl get pods -A` output and
confuse monitoring dashboards. Tracking them down manually across 15 namespaces takes
5-10 minutes.

**How to test it:**

After step 5 (ghost-node evicted pod seeded):

```bash
# Ask Claude: "List evicted pods in demo-staging"
```

Expected:

```json
[
  {
    "ref": {"kind": "Pod", "name": "stale-pod-1", "namespace": "demo-staging"},
    "eviction_reason": "Evicted",
    "eviction_message": "disk pressure seeded for demo",
    "age_hours": 0.1,
    "node_name": "ghost-node-never-exists",
    "owner_kind": null,
    "owner_name": null
  }
]
```

**Known limits:**

- Detects `phase=Failed` + `reason=Evicted` only. Pods stuck in `Pending`,
  `OOMKilled`, or `Error` state are not returned — use `kubectl get pods -A` for
  those.
- The ghost-node seeding trick used in the quickstart produces a pod that looks
  evicted but has no actual resource cost. Real evicted pods from disk pressure will
  show the same structure.

---

### Tool 6 — `propose_cleanup_plan`

**What it does:** Builds a cleanup plan from the evicted-pod list. Applies age gate
(`min_age_hours`, default 1.0), per-namespace rate limit
(`max_deletes_per_namespace`, default 20), and an allowlist gate
(`UTILITY_CLEANUP_NAMESPACE_ALLOWLIST` env var — if set, only those namespaces
are candidates). Returns each pod as `will_delete=true/false` with the skip reason.
No writes.

**Why this matters:** Most "clean up evicted pods" scripts are `kubectl delete pods
--field-selector status.phase=Failed -A`. That command has no age gate and no rate
limit. This tool cannot, by construction, delete a pod that is not already in
`Failed/Evicted` state.

**How to test it:**

```bash
# Ask Claude: "Propose a cleanup plan for evicted pods in demo-staging"
```

Expected:

```json
{
  "namespace": "demo-staging",
  "min_age_hours": 1.0,
  "max_deletes_per_namespace": 20,
  "candidates": [
    {
      "pod": {"ref": {"name": "stale-pod-1"}},
      "will_delete": true,
      "skip_reason": null
    }
  ]
}
```

If the pod is less than 1 hour old, `will_delete=false` and
`skip_reason="age_gate: 0.1h < 1.0h minimum"`.

**Known limits:**

- The plan expires when pods are added or deleted externally between planning and
  execution. Always propose and execute in the same session.

---

### Tool 7 — `execute_cleanup_plan`

**What it does:** Applies the plan from tool 6. Deletes pods where
`will_delete=true`. Dry-run by default. Each delete is independent — one failure
does not block the rest.

**How to test it:**

```bash
# Dry run
# Ask Claude: "Execute the cleanup plan in dry_run mode"
# Expected: all statuses are "skipped_dry_run"

# Real run
# Ask Claude: "Execute the cleanup plan with dry_run=false"
# Expected: status="deleted" for stale-pod-1
kubectl -n demo-staging get pods  # stale-pod-1 should be gone
```

**Known limits:**

- No rollback. A deleted pod is gone. Evicted pods have no running workload, so
  there's nothing to roll back to — the kubelet already killed the container.
  Owner workloads (Deployments, StatefulSets) will reschedule if configured.

---

### Tool 8 — `list_noisy_alerts`

**What it does:** Queries Prometheus for `ALERTS{alertstate="firing"}` over the past
N hours using `count_over_time`, normalizes to fires per hour, and returns alerts
above the `min_flaps_per_hour` threshold. Sorts by flap rate descending.

**Why this matters:** Alert fatigue kills on-call. A single chatty alert that fires
60 times overnight means the next real alert gets ignored. This tool surfaces the
specific alerts causing noise, with their flap rate, so tuning is data-driven.

**How to test it:**

With Prometheus running and some scrape intervals passing:

```bash
# Ask Claude: "List alerts that have been noisy in the last 24 hours"
```

On a fresh k3d cluster you may see 0 results (no alerts have fired). To seed
test data you'd need to deliberately trigger an alert rule, which is environment-
specific.

**Known limits:**

- Returns empty list if Prometheus is unreachable or `PROMETHEUS_URL` is unset.
- Requires Prometheus to have `ALERTS` metric populated — this is standard when
  using Alertmanager rules but absent on clusters with no alert rules.
- The `count_over_time` approach counts scrape samples (one per evaluation
  interval, typically 1m). A very long `for:` duration on a fast-firing alert
  may produce lower flap counts than expected.

---

### Tool 9 — `propose_alert_tuning`

**What it does:** Takes the noisy-alert list from tool 8 and recommends a new
`for:` duration for each alert. Critical-severity alerts are flagged
`requires_human_review=true` — no `for:` change is suggested automatically.
LLM narration if a provider is configured; deterministic summary otherwise.

**Why this matters:** The standard fix for a chatty alert is increasing its `for:`
duration. The right value depends on how long the underlying condition typically
lasts before self-healing. This tool provides a starting point: current `for:`,
observed flap rate, and a recommended new `for:`.

**Known limits:**

- No apply path. The output is advisory only. Applying changes to Prometheus alert
  rules requires editing the PrometheusRule CRD or Alertmanager config — that step
  is intentionally outside the scope of this tool to preserve human oversight on
  alert thresholds.
- Cannot read the current `for:` value from Prometheus directly (it's not exposed
  via the query API). Shows `current_for=null` when unknown.

---

### Tool 10 — `list_old_opensearch_indices`

**What it does:** Queries OpenSearch's `_cat/indices` endpoint and returns indices
older than `older_than_days` days matching any of the `index_patterns` (fnmatch
globs, e.g. `["logs-*", "metrics-*"]`). Checks for retention tags in both index
`_settings` and mapping `_meta`. Returns empty list on any error.

**How to test it:**

Requires OpenSearch or Elasticsearch running. With a local OpenSearch:

```bash
export OPENSEARCH_URL=http://localhost:9200
# Ask Claude: "List log indices older than 30 days matching logs-*"
```

**Known limits:**

- Requires `OPENSEARCH_URL` env var. Returns empty list if unset.
- Index creation date comes from OpenSearch's `settings.index.creation_date` (epoch
  ms). Indices whose metadata is missing or corrupted will have `age_days=null` and
  will be excluded from cleanup candidates.
- Does not support OpenSearch clusters that require mTLS client auth. Only supports
  basic auth via `OPENSEARCH_USER` + `OPENSEARCH_PASSWORD`.

---

### Tool 11 — `propose_retention_cleanup`

**What it does:** Builds a retention cleanup plan. Applies pattern gate (only indices
matching the provided globs are candidates), retention-tag safety (skips indices with
any `retention`, `compliance`, `legal_hold`, or `legal-hold` marker in settings or
mapping _meta), and per-call `max_deletes` limit. Returns `will_delete` and
`skip_reason` per candidate. LLM narration if configured.

**Known limits:**

- The pattern gate requires you to explicitly pass patterns. If you pass `["*"]`
  it will match all indices — including system indices. Always pass specific patterns.
- Retention-tag detection checks known key names. A custom tag like `archive: true`
  would not be detected. Add it to the `tag_keys` tuple in `opensearch_retention/scan.py`
  if needed.

---

### Tool 12 — `execute_retention_cleanup`

**What it does:** Deletes indices from the plan where `will_delete=true`. Dry-run by
default. Each delete is independent.

**Known limits:**

- Index deletion in OpenSearch is immediate and irreversible. Always run with
  `dry_run=true` first and verify the candidate list before committing.
- `max_deletes` defaults to 50 per call. For clusters with hundreds of old indices,
  you may need multiple calls.

---

### Tool 13 — `draft_postmortem`

**What it does:** Synthesizes K8s events, Prometheus metrics, OpenSearch log counts,
and audit-ledger rows for a configurable time window into a Google SRE-style
postmortem markdown. Every source is independently optional — the tool renders valid
markdown even if all external systems are unreachable.

**Why this matters:** Writing a postmortem after a 2am incident means reconstructing
what happened from 4 different dashboards at 9am when memory has faded. This tool
pulls the timeline automatically while events are still fresh.

**How to test it:**

```bash
# Ask Claude: "Draft a postmortem for the last 30 minutes in the demo-staging namespace"
```

Expected: a markdown document with sections for Timeline, Events, Metrics, and
Next Steps. On a quiet cluster, most sections will note "no events found" — that's
correct.

**Known limits:**

- LLM narration requires `UTILITY_LLM_PROVIDER` to be configured (see LLM setup).
  Without it, a deterministic template is used — it's less readable but contains
  the same structured data.
- K8s events older than 1 hour may be garbage-collected by the cluster before this
  tool runs.
- Prometheus queries use instant queries (point-in-time), not range queries. The
  metrics section shows the latest value of a few key metrics, not a full time-series.

---

### Tool 14 — `check_control_plane_cert_expiry`

**What it does:** On kubeadm clusters: probes every master node by creating a
short-lived, read-only, privileged Pod in kube-system. The Pod mounts the host
filesystem at `/host`. The tool runs `chroot /host openssl x509 -enddate -noout`
for each of the 4 standard kubeadm cert files. Returns days-to-expiry per cert
per node.

**On k3d/k3s:** Returns `source="unsupported_cluster_type"` with the message
"k3s uses `k3s certificate rotate`". No Pods are created.

**On EKS/GKE/AKS:** Returns `source="unsupported_cluster_type"` with a message
explaining that cloud providers manage CP certs.

**How to test it (kubeadm/kind only):**

```bash
# On a kind cluster with 3 control planes (see tests/demo/demo-cp-up.sh):
# Ask Claude: "Check control-plane cert expiry"
```

Expected (kubeadm cluster, 1 year after install):

```json
[
  {
    "node": "control-plane-0",
    "certs": {
      "apiserver": "2027-04-20T12:00:00Z",
      "apiserver-kubelet-client": "2027-04-20T12:00:00Z",
      "front-proxy-client": "2027-04-20T12:00:00Z",
      "etcd-server": "2027-04-20T12:00:00Z"
    },
    "soonest_days_until_expiry": 365,
    "source": "probed"
  }
]
```

Expected on k3d:

```json
[
  {
    "node": "k3d-utility-demo-server-0",
    "certs": {},
    "soonest_days_until_expiry": null,
    "source": "unsupported_cluster_type",
    "refusal_reason": "This cluster appears to be k3s/k3d..."
  }
]
```

**Known limits:**

- The probe Pod requires `privileged: true`. Clusters with PodSecurity Admission
  in `Restricted` mode on kube-system will reject the Pod.
- Probing takes 20-40 seconds per node (Pod scheduling + openssl exec).
- Only checks the 4 standard kubeadm-generated certs. Does not check the cluster CA
  itself (`ca.crt`), etcd CA, or kubelet serving certs.

---

### Tool 15 — `generate_control_plane_rotation_runbook`

**What it does:** Emits the exact 14-step kubeadm rotation sequence as a structured
plan + Markdown runbook. Pure read — no cluster mutations. The runbook includes
pre-flight checklist and verification steps.

**On k3d/EKS/GKE/AKS:** Returns structured refusal. The runbook is not generated.

**How to test it:**

```bash
# Ask Claude: "Generate the control-plane rotation runbook for master-0"
```

Expected: 14 steps starting with `kubeadm certs check-expiration` and ending with
`crictl ps | egrep 'etcd|kube-apiserver|...'`.

**Known limits:**

- The runbook assumes kubeadm 1.26+. Step commands may differ on older kubeadm
  versions (e.g., `kubeadm alpha certs` vs `kubeadm certs`).

---

### Tool 16 — `execute_control_plane_rotation`

**What it does:** Runs the 14-step runbook on one master via a privileged executor
Pod. Four safety gates (in order):

0. **Cluster type gate** — refuses on k3s/managed clusters before any cluster mutation.
1. **Business-hours gate** — refuses during UTC 13:00-21:00 Mon-Fri unless
   `force_during_business_hours=true`.
2. **Cluster health gate** — all master nodes must be Ready; etcd quorum must be
   intact (N//2 + 1 healthy endpoints).
3. **Concurrency gate** — no other rotation Pod may be active in kube-system.

Dry-run by default. On step failure: attempts best-effort rollback (restores static
pod manifests, restarts kubelet), returns `status="rolled_back"`.

**On k3d:** Returns `status="refused_unsupported_cluster_type"` immediately. No Pods
created.

**How to test it (dry run):**

```bash
# Safe on any cluster — dry run hits cluster-type gate on k3d, stops there
# Ask Claude: "Execute control-plane rotation on master-0 in dry_run mode"
# On k3d: status="refused_unsupported_cluster_type"
# On kubeadm: status="planned_dry_run", 14 steps with status="skipped_dry_run"
```

**Known limits:**

- Real execution requires SSH access to the host (via the privileged Pod with host
  filesystem mount). This is equivalent to having root on the node.
- The executor Pod runs `systemctl restart kubelet`. This causes a brief (< 10s)
  disruption to workloads on the rotated node during kubelet restart.
- `crictl` must be available on the host (standard on containerd-based clusters).
- The etcd quorum check runs `etcdctl` inside the etcd Pod. On single-node clusters
  or unusual etcd configurations, this may return non-JSON output — the tool handles
  this gracefully (rc=0 + non-JSON = assume quorum OK).

---

### Tool 17 — `build_vault_cert_bundle`

**What it does:** Post-rotation step. Reads `apiserver.crt` PEM from each master
node via the same privileged probe approach as tool 14. Concatenates with per-node
separator headers, base64-encodes. Returns the blob and instructions for pasting
into a Vault team's ticket (for the External Secrets Operator pipeline).

**On k3d:** Returns empty `node_certs`, empty `bundle_b64`, and the refusal message
as `vault_instruction`. No Pods created.

**Known limits:**

- Only retrieves `apiserver.crt`. The full cert chain (apiserver CA, front-proxy CA,
  etcd CA) would require separate calls or a future `--all-certs` mode.

---

## LLM provider setup

All 17 tools work without an LLM. Narration (plain-English summaries) is the only
LLM-dependent feature. Every tool has a deterministic fallback.

Set `UTILITY_LLM_PROVIDER` to enable narration:

| Provider | Env var | Required env |
|---|---|---|
| Anthropic | `UTILITY_LLM_PROVIDER=anthropic` | `ANTHROPIC_API_KEY` |
| OpenAI | `UTILITY_LLM_PROVIDER=openai` | `OPENAI_API_KEY` |
| Vertex AI | `UTILITY_LLM_PROVIDER=vertex` | GCP ADC or `GOOGLE_APPLICATION_CREDENTIALS` |
| Ollama | `UTILITY_LLM_PROVIDER=ollama` | `OLLAMA_HOST` (default http://localhost:11434) |
| Disabled | unset or `UTILITY_LLM_PROVIDER=disabled` | — |

Verify:

```bash
UTILITY_LLM_PROVIDER=anthropic mcp-k8s-utility llm-probe
# Expected: "narrated" and a short test response
```

---

## RBAC / production install

```bash
kubectl apply -f deploy/rbac.yaml
```

See `docs/rbac.md` for:
- What each permission is used for
- How to harden by splitting into two ServiceAccounts (read-only + write)
- How to scope CP rotation to kube-system only
- How to audit via the SQLite ledger

---

## Environment variables reference

| Variable | Default | Used by |
|---|---|---|
| `KUBECONFIG` | `~/.kube/config` | All k8s tools |
| `PROMETHEUS_URL` | — | All Prometheus tools |
| `PROMETHEUS_BEARER_TOKEN` | — | PromClient auth (bearer) |
| `PROMETHEUS_USER` | — | PromClient auth (basic) |
| `PROMETHEUS_PASSWORD` | — | PromClient auth (basic) |
| `OPENSEARCH_URL` | — | All OpenSearch tools |
| `OPENSEARCH_USER` | — | OpenSearch auth |
| `OPENSEARCH_PASSWORD` | — | OpenSearch auth |
| `UTILITY_LLM_PROVIDER` | `disabled` | Narration in right-size, alert-tuning, retention, postmortem |
| `UTILITY_BUSINESS_HOURS_START_UTC` | `13` | Business-hours gate |
| `UTILITY_BUSINESS_HOURS_END_UTC` | `21` | Business-hours gate |
| `UTILITY_BUSINESS_HOURS_DAYS` | `0,1,2,3,4` | Business-hours gate (0=Mon) |
| `UTILITY_CLEANUP_NAMESPACE_ALLOWLIST` | — | Cleanup allowlist (comma-separated) |
| `UTILITY_MAX_RETENTION_DELETES` | `50` | OpenSearch retention per-call limit |

---

## Troubleshooting

**`list_expiring_certificates` returns empty:**
- Is cert-manager installed? `kubectl get crd certificates.cert-manager.io`
- Does the server have RBAC to list Certificate CRDs? `kubectl auth can-i list certificates.cert-manager.io`
- Are there any certificates? `kubectl get certificates -A`

**`propose_right_size_plan` returns empty recommendations:**
- Is `PROMETHEUS_URL` set and reachable? `curl "${PROMETHEUS_URL}/api/v1/query?query=up"`
- Does Prometheus have `container_cpu_usage_seconds_total` data? Check Prometheus targets page.

**CP rotation tool returns `refused_unsupported_cluster_type` unexpectedly:**
- The tool detected k3s or managed-cluster signals. Check: `kubectl get nodes -o json | jq '[.items[].metadata | {labels, annotations}]'`
- k3d/k3s sets `k3s.io/node-args` annotation on nodes. This is the correct detection behavior.

**Executor Pod stays Pending during CP rotation:**
- Is there a PodSecurity policy or admission webhook blocking privileged Pods in kube-system?
- Check: `kubectl -n kube-system get events --sort-by='.lastTimestamp' | tail -20`

**Claude doesn't show all 17 tools:**
- Restart Claude Desktop after editing `claude_desktop_config.json`.
- Check the MCP server started: `mcp-k8s-utility serve-mcp` should not exit.
- Check Claude's developer console for connection errors.

---

## Architecture

```
Claude Desktop / any MCP host
        │  (MCP stdio transport)
        ▼
  mcp_server.py  (FastMCP, 17 @mcp.tool handlers)
        │
        ├── Kubernetes API  (kubernetes-asyncio, KUBECONFIG)
        │     read: all tools
        │     write: cert patch, pod delete/create, pod exec
        │
        ├── Prometheus HTTP API  (PromClient, PROMETHEUS_URL)
        │     right_size, alert_tuning, postmortem
        │
        ├── OpenSearch HTTP API  (OpenSearchClient, OPENSEARCH_URL)
        │     retention, postmortem
        │
        ├── LLM provider  (UtilityLLM, UTILITY_LLM_PROVIDER)
        │     narration only — never shown cluster credentials
        │
        └── mcp-k8s-secure-ops broker  (sidecar or in-process)
              OPA policy check → short-lived token → audit row
              used by: execute_certificate_renewal (dependent rollout step)
```

Every destructive write goes through one of:
- Kubernetes RBAC (pod delete via the ServiceAccount)
- The secure-ops broker (deployment restart, cert annotation)

The LLM receives only the tool return values (structured data, no kubeconfig, no tokens).

---

Apache-2.0. Maintainer: vellankikoti@gmail.com
