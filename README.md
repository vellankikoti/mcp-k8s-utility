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

Kubernetes (the software that runs your containerized applications across many
machines) comes in many flavours. 13 of the 17 tools in this kit work on any
Kubernetes cluster — local, cloud, or bare-metal. The other 4 tools (#14–17)
handle control-plane certificate rotation, which is only possible when Kubernetes
was installed with kubeadm (kubeadm is the standard tool for installing Kubernetes
yourself on your own machines, as opposed to managed services like EKS, GKE, or
AKS). On managed clusters or k3d/k3s, those 4 tools return a structured refusal
message and do nothing else.

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
- [RBAC and production install](#rbac-and-production-install)
- [Environment variables reference](#environment-variables-reference)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)

---

## What's actually validated

How to read this table: "yes" means the tool was run on that platform in CI and
produced correct output. "yes (needs X)" means the tool works but requires that
add-on to be installed first. "refused" means the tool detects the platform and
returns a safe error — no Pods are created and nothing in the cluster is changed.
Seeing "refused" on a k3d or cloud cluster is the correct, expected behaviour for
the control-plane tools.

| Tool | k3d/k3s | kubeadm/kind | EKS/GKE/AKS | Notes |
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

"Refused" means the tool returns `status="refused_unsupported_cluster_type"` with
an explanation of why and what to do instead. No Pods are created and nothing is
mutated.

---

## Quick install

```bash
# Run once without installing (uses uvx, Python 3.11)
uvx --python 3.11 mcp-k8s-utility version

# Install into a virtual environment (isolated Python sandbox)
python3.11 -m venv .venv && source .venv/bin/activate
pip install 'mcp-k8s-utility==0.5.0'
mcp-k8s-utility version
# mcp-k8s-utility 0.5.0

# Pull the container image
docker pull ghcr.io/vellankikoti/mcp-k8s-utility:v0.5.0
```

---

## Quickstart on a 3-node k3d cluster

This walkthrough gets you from zero to a working demo in about 15 minutes on any
laptop that can run Docker. You will create a real multi-node Kubernetes cluster
locally, install the supporting add-ons (cert-manager and Prometheus), seed some
test data, connect the toolkit, and step through each tool.

### 1. Check prerequisites

Before you start, confirm these tools are installed. The version numbers are the
ones we tested; newer patch versions should work fine.

| Tool | Tested version | Install |
|---|---|---|
| k3d | 5.6.x | `brew install k3d` |
| kubectl | 1.30.x | `brew install kubectl` |
| Helm | 3.15.x | `brew install helm` |
| Python | 3.11+ | `brew install python@3.11` |

k3d runs Kubernetes inside Docker containers on your machine — no cloud account
required. kubectl is the standard command-line client for Kubernetes. Helm is the
package manager for Kubernetes add-ons.

### 2. Create a 3-machine Kubernetes cluster on your laptop

We are going to use k3d to spin up a real Kubernetes cluster entirely inside
Docker containers. The cluster will have one "server" node (the brain that makes
scheduling decisions) and two "agent" nodes (the workers that run your
applications). The `--port` flag forwards port 9090 from inside the cluster to
your laptop so Prometheus is reachable from your browser if you want it.

```bash
k3d cluster create utility-demo \
  --servers 1 \
  --agents 2 \
  --port "9090:9090@loadbalancer" \
  --wait

kubectl config use-context k3d-utility-demo
kubectl get nodes
```

Success looks like this — three machines, all in "Ready" status:

```
NAME                        STATUS   ROLES                  AGE   VERSION
k3d-utility-demo-agent-0    Ready    <none>                 30s   v1.29.x
k3d-utility-demo-agent-1    Ready    <none>                 30s   v1.29.x
k3d-utility-demo-server-0   Ready    control-plane,master   45s   v1.29.x
```

If Docker is not running, you will see a connection error — start Docker Desktop
and try again. If `k3d` is not found, run `brew install k3d`.

### 3. Install cert-manager

cert-manager is a popular add-on that issues and renews TLS certificates for
workloads inside Kubernetes. Think of it as "Let's Encrypt for your cluster." We
need it so Tools 1–3 have real certificates to scan.

The `crds.enabled=true` flag tells Helm to also install the CRDs (Custom Resource
Definitions) — the templates that teach Kubernetes about new object types like
"Certificate" and "ClusterIssuer". Without the CRDs, cert-manager cannot work.

```bash
helm repo add jetstack https://charts.jetstack.io --force-update
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set crds.enabled=true \
  --wait
```

Next, create a self-signed issuer and a short-lived test certificate. We set the
duration to 24 hours so the certificate shows up immediately in the "expiring
soon" list — you would never do this in production:

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

Success: the last command exits without an error and prints
`certificate/demo-tls condition met`.

### 4. Install Prometheus

Prometheus is the most common open-source system for collecting metrics from
running applications. It scrapes (polls) every node and Pod every few seconds and
stores the numbers. Tools 4, 8, and 9 query Prometheus to calculate CPU/memory
usage and alert flap rates.

We are installing the "kube-prometheus-stack" Helm chart, which bundles Prometheus
and all the rules needed to monitor Kubernetes itself. We disable Grafana and
Alertmanager to keep the install fast — they are not needed for this demo.

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
helm install kube-prom prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --set grafana.enabled=false \
  --set alertmanager.enabled=false \
  --set prometheus.service.type=NodePort \
  --wait --timeout=5m
```

After Helm finishes, find Prometheus's network address and export it so the
toolkit can find it:

```bash
PROM_PORT=$(kubectl -n monitoring get svc kube-prom-kube-prometheus-prometheus \
  -o jsonpath='{.spec.ports[0].nodePort}')
PROM_NODE=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[0].address}')
echo "http://${PROM_NODE}:${PROM_PORT}"
# Export for mcp-k8s-utility:
export PROMETHEUS_URL="http://${PROM_NODE}:${PROM_PORT}"
```

Verify Prometheus is responding:

```bash
curl -s "${PROMETHEUS_URL}/api/v1/query?query=up" | python3 -m json.tool | head -20
```

You should see JSON with `"status": "success"` and a list of targets.

### 5. Seed a fake evicted pod

A Pod is Kubernetes' smallest running unit — one or more containers grouped
together. When a node runs out of disk space, Kubernetes evicts (forcibly stops)
some Pods to free room. Evicted Pods stick around as tombstones — they use no CPU
or memory but still clutter the Pod list. Tools 5–7 find and clean them up.

To test without triggering real disk pressure, we create a Pod that points at a
node that does not exist. When we then patch its status to "Evicted," it looks
identical to a real evicted Pod but costs nothing:

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

Success: `kubectl -n demo-staging get pods` shows `stale-pod-1` in status `Failed`.

### 6. Install mcp-k8s-utility

```bash
pip install 'mcp-k8s-utility==0.5.0'
mcp-k8s-utility version
```

You should see `mcp-k8s-utility 0.5.0` printed. If you see "command not found,"
your Python bin directory is not on your PATH — try `python3 -m mcp_k8s_utility
version` instead.

### 7. Connect to Claude Desktop

Claude Desktop is the desktop application for Claude. We connect it to
mcp-k8s-utility using the MCP (Model Context Protocol) standard, which lets the
AI call our 17 tools like functions. The connection happens over a local stdio
pipe — the AI talks to a local process, never directly to Kubernetes.

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (create
it if it does not exist):

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

Replace `YOUR_USER` with your macOS username and `PROM_NODE:PROM_PORT` with the
address you found in step 4.

Restart Claude Desktop fully (Quit from the menu bar, not just close the window).
You should see a hammer icon and "17 tools available" in the Claude context panel
on the left side.

### 8. Walk through each tool in order

Start with read-only tools to verify everything is wired up, then move to the
ones that write to the cluster. Always run dry-run first on any execute tool.

1. `list_expiring_certificates` — confirms cert-manager is reachable
2. `list_evicted_pods` — confirms Kubernetes API access is working
3. `propose_right_size_plan` — confirms Prometheus is reachable
4. `list_noisy_alerts` — confirms Prometheus has alert data
5. `propose_cleanup_plan` — confirms the evicted-pod seed was created correctly
6. `propose_certificate_renewal` — confirms dependent-workload scanning
7. `draft_postmortem` — synthesises all available data sources at once
8. `execute_cleanup_plan` — run with `dry_run=true` first, then `dry_run=false`
9. `execute_certificate_renewal` — run with `dry_run=true` first
10. Control-plane tools (#14–17) — skip on k3d; they return a clean refusal message

---

## Per-tool workbook

Each tool entry below follows the same structure: what it does, what problem it
solves, how to try it, what success looks like, how much time it saves, and its
honest limitations.

---

### Tool 1 — `list_expiring_certificates`

**In one sentence:** Scans your cluster for TLS certificates managed by
cert-manager and returns every one that will expire within a window you choose.

**The problem this solves:**
cert-manager is supposed to auto-renew certificates, but the renewal can fail
silently — wrong issuer configuration, a misconfigured webhook, or a rate limit
hit against Let's Encrypt. The first sign of trouble is often a TLS handshake
failure in production, which shows up in your monitoring at 3 am, not in the
cert-manager logs at 2 pm the day before. This tool gives you a daily answer to
"are any certs about to expire?" without requiring you to know the exact kubectl
command for Certificate objects.

**What you type:**

```
"List certificates expiring within 30 days"
```

Or, if you prefer the CLI directly:

```bash
mcp-k8s-utility serve-mcp  # Start the server, then call via Claude
```

**What happens behind the scenes:**

1. The tool connects to the Kubernetes API using your KUBECONFIG.
2. It lists all `Certificate` objects (a CRD — Custom Resource Definition — is how
   Kubernetes is extended with new kinds of objects; cert-manager adds a
   `Certificate` CRD, for example) across all namespaces (or just one if you pass
   `namespace`).
3. For each certificate, it reads the `status.notAfter` field to find the expiry
   date.
4. It filters to only those expiring within `within_days` days (default: 30).
5. It returns a structured list sorted by soonest-to-expire first.

**Try it on your k3d cluster:**

```bash
# Make sure you ran step 3 of the quickstart (short-lived cert seeded)
# Then ask Claude:
# "List certificates expiring within 30 days in the default namespace"
```

**What you should see:**

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

**Time this saves:**
On a cluster with 30+ certificates, a manual check requires looping over every
namespace with `kubectl get certificates -A` and parsing the output. That takes
3–5 minutes. This tool takes under 5 seconds. The bigger saving is the discipline:
teams that have this as a daily check catch renewal failures a week before they
become incidents.

**Known limits:**

- Only reads cert-manager `Certificate` CRDs. Does not scan raw Kubernetes Secrets
  for manually created TLS certs, Ingress TLS annotations, or Istio service-mesh
  certificates.
- Returns an empty list if cert-manager CRDs are not installed — it will not error,
  so make sure you verify with `kubectl get crd certificates.cert-manager.io` if
  you get an unexpected empty result.

---

### Tool 2 — `propose_certificate_renewal`

**In one sentence:** Builds a complete renewal plan for expiring certificates,
including the list of application Deployments that will need to be restarted after
the cert refreshes.

**The problem this solves:**
Renewing a cert has two steps: tell cert-manager to re-issue it, then restart every
application that loaded the old cert into memory. Most operators remember step one
and forget step two — the new cert sits in the Kubernetes Secret, but the
application is still serving the old one from its in-memory cache. The result is
HTTPS errors that are baffling to debug. This tool automates the "find which
Deployments are affected" step so nothing gets missed.

**What you type:**

```
"Propose a renewal plan for certificates expiring within 30 days"
```

**What happens behind the scenes:**

1. Calls `list_expiring_certificates` internally to get the candidate list.
2. For each certificate, reads the Secret name that holds the cert's data.
3. Scans every Deployment in the cluster for volume mounts, `envFrom`, or
   `env valueFrom` references that point to that Secret.
4. Groups each cert with its list of affected Deployments.
5. Returns a structured plan — no changes are made to the cluster yet.

**Try it on your k3d cluster:**

```bash
# Ask Claude:
# "Propose a renewal plan for certificates expiring within 30 days"
```

**What you should see:**

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

`dependent_rollouts` is empty here because no Deployment in the demo cluster
mounts `demo-tls-secret`. In a production cluster you would see a list of
Deployment names that need to be rolled.

**Time this saves:**
Finding all Deployments that reference a given Secret manually requires a script
or careful grepping through YAML. In a cluster with 50+ Deployments, that takes
10–20 minutes per certificate. This tool does it in seconds.

**Known limits:**

- Scans Deployments only. StatefulSets, DaemonSets, and Jobs are not correlated
  with cert secrets in this tool (they are covered by other tools but not wired
  to cert dependency scanning yet).
- The annotation-only approach to triggering renewal works with cert-manager 1.13
  and newer. Older versions require `kubectl cert-manager renew`.

---

### Tool 3 — `execute_certificate_renewal`

**In one sentence:** Applies the renewal plan from Tool 2 — patches the cert to
force re-issue and restarts the affected Deployments — with three safety gates
you go through before any cluster change happens.

**The problem this solves:**
Even when you have a renewal plan, the manual execution is error-prone: you need
to patch the annotation at the right time, wait for cert-manager to issue the new
cert, then restart each Deployment in the right order. Doing this manually under
pressure (an expiry in 6 hours) is how mistakes happen. This tool serialises the
steps and enforces the gates automatically.

**What you type:**

```
"Execute the renewal plan with dry_run=false"
```

**What happens behind the scenes:**

1. Dry-run check: if `dry_run=true`, returns a plan with `status="skipped_dry_run"`
   for every step — nothing is written.
2. Business-hours gate: if it is currently between 13:00 and 21:00 UTC on a
   weekday, returns `refused=true` unless `force=true` was explicitly passed.
3. For each certificate in the plan:
   a. Patches the `cert-manager.io/force-renew-at` annotation to trigger re-issue.
   b. Passes dependent Deployment restarts through the `mcp-k8s-secure-ops` broker,
      which checks an OPA policy and writes an audit row before allowing the change.

**Try it on your k3d cluster:**

```bash
# Always run dry_run first:
# "Execute the renewal plan in dry_run mode"
# Expected: each step shows status="skipped_dry_run"

# Real run (outside business hours, or with force=true):
# "Execute the renewal plan with dry_run=false"
```

**What you should see (dry run):**

```json
{
  "steps": [
    {
      "certificate": "demo-tls",
      "status": "skipped_dry_run",
      "annotation_patched": false,
      "rollouts_restarted": []
    }
  ]
}
```

**Time this saves:**
This is mostly about correctness, not speed. The manual process takes 5–10 minutes
per certificate. The tool's value is eliminating the class of errors where the cert
renewed but the service kept using the old one.

**Known limits:**

- The business-hours window defaults to 13:00–21:00 UTC Monday–Friday. Change it
  with `UTILITY_BUSINESS_HOURS_START_UTC`, `UTILITY_BUSINESS_HOURS_END_UTC`, and
  `UTILITY_BUSINESS_HOURS_DAYS` environment variables.
- Dependent Deployment restarts require the `mcp-k8s-secure-ops` broker. Without it,
  the annotation patch still happens but the rollout step is skipped with a note.

---

### Tool 4 — `propose_right_size_plan`

**In one sentence:** Looks at 7 days of real CPU and memory usage from Prometheus
and tells you which Deployments are wildly over-provisioned (wasting money) or
dangerously under-provisioned (at risk of being killed).

**The problem this solves:**
Kubernetes lets you set resource "requests" (what a Pod is guaranteed) and "limits"
(the hard cap). Teams usually set these once at deploy time, never revisit them, and
end up with Pods requesting 4 CPU cores that idle at 0.05. Meanwhile, other Pods
hit their memory limit and get OOMKilled (killed by the OS for using too much
memory) at 2 am. This tool gives you p99-based numbers — the actual peak the
workload hit 99% of the time — so your sizing decisions are grounded in data.

**What you type:**

```
"Propose right-sizing for the monitoring namespace"
```

**What happens behind the scenes:**

1. Queries Prometheus for `container_cpu_usage_seconds_total` over the past 7 days.
2. Queries Prometheus for `container_memory_working_set_bytes` over the same window.
3. Calculates p95 and p99 for each container in each Deployment.
4. Computes recommended values: p99 CPU + 25% headroom, p99 memory + 20% headroom,
   with minimum floors of 10m CPU and 16 MiB memory.
5. Returns a list of recommendations with current values, observed peaks, and
   suggested new values side by side.

**Try it on your k3d cluster:**

```bash
# With Prometheus running (step 4 of quickstart):
# Ask Claude: "Propose right-sizing for the monitoring namespace"
```

**What you should see:**

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

**Time this saves:**
On a team with 20 Deployments across 5 namespaces, a manual right-sizing exercise
— querying Prometheus, building a spreadsheet, calculating headroom — takes a full
afternoon. This tool produces the same output in under a minute. Most teams do this
exercise quarterly at best; with this tool, you can do it weekly.

**Known limits:**

- Requires Prometheus with `container_cpu_usage_seconds_total` and
  `container_memory_working_set_bytes` metrics. These are standard in any
  kube-prometheus-stack install.
- This tool only reads and recommends. It does not apply changes. Use `kubectl set
  resources` or edit the Deployment YAML to apply the recommendations.
- A freshly created workload with fewer than 7 days of history will show p99=0
  and recommend the minimum floors — not a useful signal. Wait for the workload to
  age before trusting the output.

---

### Tool 5 — `list_evicted_pods`

**In one sentence:** Finds every Pod in the cluster that has been evicted and not
yet cleaned up, across all namespaces, in one read-only call.

**The problem this solves:**
When a Kubernetes node runs low on disk or memory, it evicts (forcibly terminates)
some Pods to protect itself. Those Pods stay in the list in "Failed/Evicted" state
indefinitely — Kubernetes does not delete them automatically. On a busy cluster,
hundreds of these tombstones accumulate over weeks, making `kubectl get pods -A`
output hard to read and confusing monitoring dashboards that count "failed" Pods.
Finding them manually across 15 namespaces takes 5–10 minutes.

**What you type:**

```
"List evicted pods in demo-staging"
```

**What happens behind the scenes:**

1. Sends a Kubernetes API list request with field selector `status.phase=Failed`
   — this filtering happens on the server, so only failed Pods are sent back over
   the network.
2. From that smaller list, filters locally for `status.reason=Evicted`.
3. For each evicted Pod, reads the age, the eviction message (which explains why
   it was evicted), and the owner workload (which Deployment or StatefulSet
   originally spawned it).
4. Returns the list. No writes.

**Try it on your k3d cluster:**

```bash
# After step 5 of the quickstart (evicted pod seeded):
# Ask Claude: "List evicted pods in demo-staging"
```

**What you should see:**

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

**Time this saves:**
On a cluster with 10 namespaces, finding evicted Pods manually takes about 5
minutes. On a 50-namespace cluster, it is closer to 20 minutes. This tool takes
under 3 seconds regardless of cluster size.

**Known limits:**

- Detects `phase=Failed` plus `reason=Evicted` only. Pods stuck in `Pending`,
  `OOMKilled`, or `Error` for other reasons are not returned here — use
  `kubectl get pods -A` for a full picture.

---

### Tool 6 — `propose_cleanup_plan`

**In one sentence:** Takes the evicted-pod list and builds a safe deletion plan,
applying age gates and per-namespace rate limits before anything is touched.

**The problem this solves:**
The naive way to clean evicted Pods is `kubectl delete pods --field-selector
status.phase=Failed -A`. That command has no age gate (it could delete a Pod that
failed 30 seconds ago, before you have had a chance to read its logs), no rate
limit, and no allowlist. This tool applies all three guards and shows you exactly
what it plans to delete and why, before a single Pod is removed.

**What you type:**

```
"Propose a cleanup plan for evicted pods in demo-staging"
```

**What happens behind the scenes:**

1. Runs `list_evicted_pods` internally to get the full candidate list.
2. Applies the age gate: any Pod younger than `min_age_hours` (default 1.0) is
   excluded with `skip_reason="age_gate"`.
3. Applies the allowlist gate: if `UTILITY_CLEANUP_NAMESPACE_ALLOWLIST` is set,
   only namespaces in that list are candidates. Others are excluded.
4. Applies the rate limit: at most `max_deletes_per_namespace` (default 20) Pods
   can be planned for deletion in a single call per namespace.
5. Returns every candidate with `will_delete=true` or `will_delete=false` and an
   explanation. No writes.

**Try it on your k3d cluster:**

```bash
# Ask Claude: "Propose a cleanup plan for evicted pods in demo-staging"
```

**What you should see:**

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

If the pod is less than 1 hour old, `will_delete=false` with
`skip_reason="age_gate: 0.1h < 1.0h minimum"`. Wait an hour and try again.

**Time this saves:**
This is mostly about correctness. The manual review — list evicted pods, check
ages, decide which ones are safe to delete — takes about 5 minutes. The tool does
it in seconds with a consistent policy.

**Known limits:**

- The plan reflects cluster state at the moment the proposal is generated. If pods
  are added or deleted between planning and execution (by Kubernetes or another
  operator), the plan may be stale. Always propose and execute in the same session.

---

### Tool 7 — `execute_cleanup_plan`

**In one sentence:** Applies the cleanup plan from Tool 6 by deleting the marked
Pods, with a mandatory dry-run mode to review before committing.

**The problem this solves:**
Having a plan is only useful if execution is equally safe. This tool makes each
Pod deletion independent — one failure does not block the rest — and defaults to
dry-run so you always have a chance to check the plan before anything is removed.

**What you type:**

```
"Execute the cleanup plan with dry_run=false"
```

**What happens behind the scenes:**

1. If `dry_run=true` (the default), iterates the plan and returns
   `status="skipped_dry_run"` for every Pod. Nothing is deleted.
2. If `dry_run=false`, deletes each Pod with `will_delete=true` via the Kubernetes
   API. Each delete is independent — if Pod 3 fails, Pods 4–20 still run.
3. Returns a result per Pod: `deleted`, `skipped_dry_run`, or `error` with the
   error message.

**Try it on your k3d cluster:**

```bash
# Dry run first:
# Ask Claude: "Execute the cleanup plan in dry_run mode"
# Expected: all statuses are "skipped_dry_run"

# Real run:
# Ask Claude: "Execute the cleanup plan with dry_run=false"
kubectl -n demo-staging get pods  # stale-pod-1 should be gone
```

**What you should see (after real run):**

```json
{
  "results": [
    {"pod": "stale-pod-1", "namespace": "demo-staging", "status": "deleted"}
  ]
}
```

**Time this saves:**
Execution of a 20-pod cleanup plan that would take 2 minutes manually takes under
10 seconds. The real saving is the safety: dry-run first means no surprises.

**Known limits:**

- There is no rollback. A deleted evicted Pod is gone. This is safe by design —
  the kubelet already killed the container when it evicted the Pod. The running
  workload (if any) is managed by a Deployment or StatefulSet and will reschedule
  automatically.

---

### Tool 8 — `list_noisy_alerts`

**In one sentence:** Finds the Prometheus alerts that have been firing and
resolving repeatedly — the ones causing your on-call to stop taking alerts
seriously.

**The problem this solves:**
Alert fatigue is one of the most dangerous failure modes in on-call culture. When
the same alert fires 60 times a night and resolves itself each time, operators
start ignoring it. The next time it fires and does not resolve — the real
incident — gets ignored too. This tool surfaces the specific alerts causing noise,
ranked by how often they fire per hour, so you have data to justify tuning them.

**What you type:**

```
"List alerts that have been noisy in the last 24 hours"
```

**What happens behind the scenes:**

1. Queries Prometheus for `ALERTS{alertstate="firing"}` over the past N hours
   using `count_over_time`. This counts how many times the alert appeared in
   Prometheus's scrape samples.
2. Normalises the count to "fires per hour."
3. Filters to alerts above `min_flaps_per_hour` (default: 1.0).
4. Sorts by flap rate, highest first.
5. Returns the list with alert name, labels, and flap rate.

**Try it on your k3d cluster:**

```bash
# With Prometheus running:
# Ask Claude: "List alerts that have been noisy in the last 24 hours"
```

On a freshly created k3d cluster with no alert rules, you will likely see an empty
list — that is correct. In a production cluster, you may see dozens of alerts here.

**What you should see (production cluster example):**

```json
[
  {
    "alert": "KubePodCrashLooping",
    "labels": {"severity": "warning", "namespace": "staging"},
    "flaps_per_hour": 12.4,
    "window_hours": 24
  }
]
```

**Time this saves:**
Identifying noisy alerts manually requires querying Prometheus, correlating firing
times with the alertmanager history, and building a frequency table. This takes
30–60 minutes for a cluster with many alerts. This tool does it in seconds.

**Known limits:**

- Returns an empty list if Prometheus is unreachable or `PROMETHEUS_URL` is unset.
- Requires Prometheus to have the `ALERTS` metric populated — this is standard when
  using Alertmanager rules but absent on clusters with no alert rules configured.
- The `count_over_time` approach counts scrape samples (one per evaluation interval,
  typically every minute). A slow-firing alert with a long `for:` duration may appear
  less noisy than it feels to your on-call.

---

### Tool 9 — `propose_alert_tuning`

**In one sentence:** Takes the noisy-alert list and recommends a new `for:` duration
for each alert, with critical alerts flagged for human review rather than automated
suggestion.

**The problem this solves:**
The standard fix for a chatty alert is increasing its `for:` duration — the time
the condition must be continuously true before the alert fires. But the right value
depends on how long the underlying problem typically lasts before self-healing. Set
it too short and the alert keeps firing on transient blips. Set it too long and you
miss real incidents. This tool provides a data-driven starting point rather than a
guess.

**What you type:**

```
"Propose tuning for the noisy alerts from the last 24 hours"
```

**What happens behind the scenes:**

1. Receives the noisy-alert list from Tool 8 (or runs it internally).
2. For each alert, looks at the flap rate and current `for:` value (if available).
3. For non-critical alerts: recommends a new `for:` duration that would have
   suppressed most of the noise based on the observed firing pattern.
4. For critical-severity alerts: sets `requires_human_review=true` and does not
   suggest a value. A human must decide whether to tune critical alerts.
5. Returns a structured list of recommendations.

**Try it on your k3d cluster:**

```bash
# Ask Claude: "Propose tuning for noisy alerts"
# (If there are no noisy alerts on k3d, the result will be empty — expected)
```

**What you should see:**

```json
[
  {
    "alert": "KubePodCrashLooping",
    "current_for": null,
    "recommended_for": "5m",
    "flaps_per_hour": 12.4,
    "requires_human_review": false,
    "reasoning": "Alert fires on average every 5 minutes; increasing for: to 5m would suppress transient blips"
  }
]
```

**Time this saves:**
This is about correctness and speed of decision-making. A manual analysis of a
noisy alert takes 20–30 minutes per alert. This tool produces a recommendation in
seconds that the operator can review and apply, cutting the tuning cycle from days
to hours.

**Known limits:**

- No apply path. The output is advisory only. To apply changes you need to edit the
  PrometheusRule CRD or Alertmanager configuration — that step is intentionally
  outside this tool to preserve human oversight on alert thresholds.
- Cannot read the current `for:` value directly from Prometheus (it is not exposed
  via the query API). Shows `current_for=null` when it cannot be determined.

---

### Tool 10 — `list_old_opensearch_indices`

**In one sentence:** Scans your OpenSearch cluster for log indices older than a
threshold you choose and returns their names, ages, and sizes.

OpenSearch is an open-source search and log-storage system, often used to hold
application logs. Over time, old log indices pile up and consume disk space.
Compliance rules usually require keeping logs for a set period — say, 90 days —
and deleting them after. This tool is the first step in that process.

**The problem this solves:**
Teams often have no visibility into how many old log indices exist or how much disk
they consume. The answer is usually "more than you think." Without a regular
cleanup, OpenSearch nodes hit disk watermarks, start refusing writes, and your logs
disappear entirely — often at the worst possible moment, like during an incident
when you need them most.

**What you type:**

```
"List log indices older than 30 days matching logs-*"
```

**What happens behind the scenes:**

1. Calls OpenSearch's `_cat/indices` endpoint with JSON output.
2. Filters by `index_patterns` (fnmatch globs, e.g. `["logs-*", "metrics-*"]`).
3. Reads the `creation_date` from each index's settings.
4. Filters to indices older than `older_than_days` days.
5. Checks for retention tags in `_settings` and mapping `_meta`.
6. Returns each matching index with name, age, size, and retention-tag status.

**Try it on your k3d cluster:**

```bash
export OPENSEARCH_URL=http://localhost:9200
# Ask Claude: "List log indices older than 30 days matching logs-*"
```

You need a local OpenSearch instance for this to return results. If `OPENSEARCH_URL`
is unset, the tool returns an empty list without error.

**What you should see:**

```json
[
  {
    "index": "logs-app-2025-10-01",
    "age_days": 170,
    "size_bytes": 2147483648,
    "has_retention_tag": false,
    "creation_date": "2025-10-01T00:00:00Z"
  }
]
```

**Time this saves:**
Querying OpenSearch for old indices, calculating their ages, and cross-referencing
with retention policies manually takes 15–30 minutes. This tool does it in seconds.

**Known limits:**

- Requires `OPENSEARCH_URL` to be set. Returns an empty list if unset.
- Index creation date comes from `settings.index.creation_date` (epoch milliseconds).
  Indices with missing or corrupted metadata will have `age_days=null` and will be
  excluded from cleanup candidates.
- Does not support OpenSearch clusters that require mTLS client authentication. Only
  supports basic auth via `OPENSEARCH_USER` and `OPENSEARCH_PASSWORD`.

---

### Tool 11 — `propose_retention_cleanup`

**In one sentence:** Builds a deletion plan from the old-indices list, skipping any
index marked with compliance or legal-hold tags, and capping the deletions per call.

**The problem this solves:**
Bulk-deleting indices is irreversible. A cleanup script that does not check for
compliance holds can delete logs that must be retained for 7 years by law — an
expensive mistake. This tool applies three layers of protection before putting
anything on the delete list: pattern gate, compliance-tag check, and a per-call
maximum.

**What you type:**

```
"Propose a retention cleanup for log indices older than 30 days"
```

**What happens behind the scenes:**

1. Gets the old-index list from Tool 10.
2. Applies the pattern gate: only indices matching your provided globs are
   candidates. Passing `["*"]` would match everything — always use specific patterns.
3. Checks each index for retention tags in `_settings` and mapping `_meta`. Tags
   checked: `retention`, `compliance`, `legal_hold`, `legal-hold`. Any match and
   the index is excluded with `skip_reason="retention_tag"`.
4. Applies the `max_deletes` cap (default 50). Candidates beyond the cap are
   excluded with `skip_reason="max_deletes_reached"`.
5. Returns every candidate with `will_delete` and `skip_reason`.

**Try it on your k3d cluster:**

```bash
# Requires OpenSearch. Ask Claude:
# "Propose a retention cleanup for logs-* indices older than 30 days"
```

**What you should see:**

```json
{
  "candidates": [
    {
      "index": "logs-app-2025-10-01",
      "will_delete": true,
      "skip_reason": null
    },
    {
      "index": "logs-legal-2025-10-01",
      "will_delete": false,
      "skip_reason": "retention_tag: legal_hold=true"
    }
  ]
}
```

**Time this saves:**
The manual version — cross-referencing an index list with a retention policy
spreadsheet, checking each index for compliance metadata — takes an hour for a
large cluster. This takes seconds and is repeatable.

**Known limits:**

- Retention-tag detection checks known key names. A custom tag like `archive: true`
  would not be detected. Add it to the `tag_keys` tuple in
  `opensearch_retention/scan.py` if your organisation uses a custom tag.

---

### Tool 12 — `execute_retention_cleanup`

**In one sentence:** Deletes the indices marked `will_delete=true` in the retention
plan, one at a time, with dry-run by default.

**The problem this solves:**
Execution of an OpenSearch cleanup needs to be audited and cautious. Index deletion
is immediate and irreversible — there is no "undo" button. This tool enforces a
dry-run-first workflow and makes each deletion independent so one failure does not
abort the rest.

**What you type:**

```
"Execute the retention cleanup with dry_run=false"
```

**What happens behind the scenes:**

1. If `dry_run=true`, iterates the plan and returns `status="skipped_dry_run"`
   for every index. Nothing is deleted.
2. If `dry_run=false`, calls the OpenSearch DELETE index API for each `will_delete=true`
   index. Each call is independent.
3. Returns a result per index: `deleted`, `skipped_dry_run`, or `error`.

**Try it on your k3d cluster:**

```bash
# Always dry-run first:
# "Execute the retention cleanup in dry_run mode"
# Then commit:
# "Execute the retention cleanup with dry_run=false"
```

**Time this saves:**
Deleting 50 indices manually via the OpenSearch API or Kibana/Dashboards takes
15–20 minutes. This tool handles 50 in under 30 seconds.

**Known limits:**

- Index deletion in OpenSearch is immediate and irreversible. Always run with
  `dry_run=true` first and review the candidate list carefully.
- `max_deletes` defaults to 50 per call. For clusters with hundreds of old indices,
  run the tool multiple times until the old-indices list is empty.

---

### Tool 13 — `draft_postmortem`

**In one sentence:** Pulls Kubernetes events, Prometheus metrics, OpenSearch log
counts, and audit rows for a time window you choose and assembles them into a
Google-SRE-style postmortem document you can edit and publish.

**The problem this solves:**
After a 2 am incident, writing a postmortem means reconstructing what happened from
four different dashboards — often the next morning, when memory has faded and logs
have been rotated. The result is a document that covers what is easy to find, not
what actually happened. This tool pulls the data while it is still fresh and
structures it in the format your team already uses.

**What you type:**

```
"Draft a postmortem for the last 30 minutes in the demo-staging namespace"
```

**What happens behind the scenes:**

1. Queries the Kubernetes API for all Events in the specified namespace and time
   window.
2. Queries Prometheus for key metrics (error rate, CPU, memory) at the current
   instant.
3. Queries OpenSearch for log counts in the window (if configured).
4. Reads the audit ledger for any tool actions taken during the window.
5. Combines all of the above into a structured markdown document with sections for
   Timeline, Events, Metrics, Logs, and Next Steps.
6. If an LLM provider is configured, narrates the document in plain English. If not,
   uses a deterministic template that contains the same data in a less readable format.

**Try it on your k3d cluster:**

```bash
# Ask Claude:
# "Draft a postmortem for the last 30 minutes in the demo-staging namespace"
```

**What you should see:**

A markdown document starting with a timeline, then sections for each data source.
On a quiet cluster, most sections will note "no events found" — that is correct and
expected. The tool renders a valid document even when all external systems return
no data.

**Time this saves:**
Writing a postmortem from scratch after an incident typically takes 1–2 hours for
a thorough document. This tool produces a first draft in under a minute. You still
need to edit it — fill in the root cause, action items, and context — but you start
from a structured skeleton, not a blank page.

**Known limits:**

- LLM narration requires `UTILITY_LLM_PROVIDER` to be configured (see
  [LLM provider setup](#llm-provider-setup)).
- Kubernetes events older than 1 hour may have been garbage-collected by the cluster
  before this tool runs. Run it promptly after an incident.
- Prometheus queries are point-in-time (instant queries), not range queries. The
  metrics section shows the latest value of a few key metrics, not a full time-series.
  Use Grafana for full time-series analysis.

---

### Tool 14 — `check_control_plane_cert_expiry`

**In one sentence:** On kubeadm clusters, checks the exact expiry date of every
control-plane certificate on every master node by reading the actual certificate
files on the hosts.

A brief word on what the control plane is: Kubernetes has two kinds of nodes —
control-plane nodes (the "brain," where scheduling decisions are made) and worker
nodes (where your apps actually run). The control plane itself uses TLS certificates
to secure its own internal communications. These certificates expire annually on
kubeadm clusters and must be manually rotated — which is what Tools 14–17 do.

A static pod is a Pod that Kubernetes runs automatically because its YAML file is
in a special folder on the node. That is how the Kubernetes control plane itself
runs — the API server, scheduler, and controller-manager are all static pods.

etcd is the database Kubernetes uses to store everything it knows. If etcd is
unhealthy, the cluster cannot make decisions.

**The problem this solves:**
Control-plane cert expiry is one of the most catastrophic and easily preventable
Kubernetes failures. When the certs expire, `kubectl` stops working, the API server
becomes unreachable, and no new Pods can be scheduled. Recovery without a backup is
complex and stressful. Checking expiry takes under a minute with this tool; without
it, most teams only find out on the day the certs expire.

**What you type:**

```
"Check control-plane cert expiry"
```

**What happens behind the scenes (kubeadm clusters only):**

1. Identifies every control-plane node in the cluster.
2. For each node, creates a short-lived, read-only Pod in the `kube-system`
   namespace that mounts the host filesystem at `/host`.
3. Runs `chroot /host openssl x509 -enddate -noout` (`chroot` is a Linux command
   that makes a process think a subfolder is its root filesystem — we use it to
   run commands as if we were on the host machine) against each of the 4 standard
   kubeadm cert files.
4. Parses the expiry dates and returns them per cert per node.
5. Deletes the probe Pod when done.

On k3d/k3s and managed clusters (EKS, GKE, AKS): returns
`source="unsupported_cluster_type"` with an explanation. No Pods are created.

**Try it on your k3d cluster:**

```bash
# On k3d, this returns a structured refusal (expected and correct):
# Ask Claude: "Check control-plane cert expiry"
```

**What you should see on k3d (expected refusal):**

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

**What you should see on a kubeadm cluster (1 year after install):**

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

**Time this saves:**
Checking cert expiry manually requires SSH access to each master node and running
`kubeadm certs check-expiration`. On a 3-master cluster, that is 5–10 minutes and
requires elevated access. This tool does it in 1–2 minutes with no SSH required.

**Known limits:**

- The probe Pod requires `privileged: true`. Clusters with PodSecurityAdmission
  (the safety check built into newer Kubernetes versions that blocks risky Pods
  from being created in sensitive namespaces) in "Restricted" mode on `kube-system`
  will reject the Pod. See the troubleshooting section for the fix.
- Probing takes 20–40 seconds per node — Pod scheduling plus `openssl` exec.
- Only checks the 4 standard kubeadm-generated certs. Does not check the cluster
  CA itself (`ca.crt`), etcd CA, or kubelet serving certs.

---

### Tool 15 — `generate_control_plane_rotation_runbook`

**In one sentence:** Generates the exact 14-step kubeadm certificate rotation
sequence as a structured plan and readable Markdown document — pure read, no
cluster changes.

**The problem this solves:**
Most platform teams have a wiki page with the rotation steps, written the last time
someone did it. The wiki page is usually 18 months out of date, missing a step,
or written for a different kubeadm version. This tool generates the steps from the
current best practices for your specific kubeadm version, including pre-flight
checks and verification steps after each stage.

**What you type:**

```
"Generate the control-plane rotation runbook for master-0"
```

**What happens behind the scenes:**

1. Detects the cluster type. On k3d or managed clusters, returns a structured
   refusal immediately — the runbook is not generated.
2. On kubeadm clusters: generates a 14-step plan starting with
   `kubeadm certs check-expiration` and ending with verification that all static
   pods restarted successfully.
3. Returns the plan as structured JSON and as a Markdown document you can paste
   into your runbook system.

**Try it on your k3d cluster:**

```bash
# On k3d, this returns a structured refusal (expected and correct):
# Ask Claude: "Generate the control-plane rotation runbook for master-0"
```

**Time this saves:**
Writing a complete, accurate rotation runbook from scratch takes 1–2 hours.
Reviewing and adapting an auto-generated one takes 15 minutes.

**Known limits:**

- The runbook assumes kubeadm 1.26 or newer. Step commands differ on older versions
  (`kubeadm alpha certs` vs `kubeadm certs`).

---

### Tool 16 — `execute_control_plane_rotation`

**In one sentence:** Runs the 14-step rotation runbook on one master node via a
privileged executor Pod, with four safety gates that must all pass before any
action is taken.

**The problem this solves:**
Control-plane cert rotation is the highest-risk routine maintenance task on a
kubeadm cluster. The steps must be run in the right order. A misstep can take
down the cluster's ability to schedule Pods. This tool serialises the steps,
checks cluster health before starting, and rolls back if anything fails.

**What you type:**

```
"Execute control-plane rotation on master-0 in dry_run mode"
```

**What happens behind the scenes (kubeadm clusters only):**

The tool applies four gates in sequence before touching anything:

**Gate 0 — Cluster type check:** If the cluster is k3s, k3d, EKS, GKE, or AKS,
returns `status="refused_unsupported_cluster_type"` immediately. No Pods created.

**Gate 1 — Business-hours check:** If it is currently 13:00–21:00 UTC on a
weekday, returns a refusal unless `force_during_business_hours=true` was passed.

**Gate 2 — Cluster health check:** All master nodes must be in Ready status.
etcd quorum must be intact (more than half of etcd endpoints must be healthy).
If either check fails, the rotation is aborted.

**Gate 3 — Concurrency check:** No other rotation Pod may be active in
`kube-system`. If one is found, the new rotation is aborted.

If all four gates pass and `dry_run=false`, the tool creates a privileged executor
Pod on the target master node, runs the 14 rotation steps via `exec`, and verifies
each step. On step failure: attempts best-effort rollback (restores static pod
manifests, restarts systemd/systemctl — systemd is how most Linux distributions
manage background services — for kubelet) and returns `status="rolled_back"`.

**Try it on your k3d cluster:**

```bash
# Safe on any cluster — dry_run hits cluster-type gate on k3d and stops.
# Ask Claude: "Execute control-plane rotation on master-0 in dry_run mode"
# On k3d: status="refused_unsupported_cluster_type"
# On kubeadm: status="planned_dry_run", 14 steps with status="skipped_dry_run"
```

**Time this saves:**
A manual rotation on a 3-master cluster takes 45–90 minutes with SSH access and
careful attention to each step. This tool reduces it to 15–20 minutes of monitoring
output while the tool does the work.

**Known limits:**

- Real execution requires privileged Pod access with the host filesystem mounted —
  equivalent to having root on the node. Ensure your RBAC is set up correctly
  before running.
- The executor Pod runs `systemctl restart kubelet`, which causes a brief (under
  10 seconds) disruption to workloads on the rotated node during kubelet restart.
- `crictl` must be available on the host. This is standard on containerd-based
  clusters; not guaranteed on older Docker-based clusters.
- The etcd quorum check runs `etcdctl` inside the etcd Pod. On single-node clusters
  or unusual etcd configurations, this may return non-JSON output — the tool treats
  this gracefully and assumes quorum is OK.

---

### Tool 17 — `build_vault_cert_bundle`

**In one sentence:** After rotation, reads the new API server certificate from each
master node and packages them into a base64-encoded bundle your Vault team can
paste into a ticket to update the External Secrets Operator pipeline.

**The problem this solves:**
After rotating control-plane certs, downstream systems that trust the old API server
certificate — most commonly Vault and its External Secrets Operator integration —
need the new cert bundle. Building this bundle manually means SSH-ing to each master,
copying the cert file, concatenating them, and encoding the result. This tool
automates all of that.

**What you type:**

```
"Build the Vault cert bundle after rotation"
```

**What happens behind the scenes:**

1. Uses the same privileged probe approach as Tool 14 to read `apiserver.crt` from
   each master node.
2. Adds a separator header between each node's cert (`# node: master-0`, etc.).
3. Base64-encodes the concatenated bundle.
4. Returns the bundle and a ready-to-paste instruction for the Vault team.

On k3d: returns empty `node_certs`, empty `bundle_b64`, and the refusal message as
`vault_instruction`. No Pods are created.

**Try it on your k3d cluster:**

```bash
# On k3d, this returns a structured refusal (expected and correct):
# Ask Claude: "Build the Vault cert bundle"
```

**Time this saves:**
Manual cert bundle assembly takes 10–15 minutes per cluster. This tool does it in
1–2 minutes.

**Known limits:**

- Only retrieves `apiserver.crt`. The full cert chain (API server CA, front-proxy
  CA, etcd CA) would require separate calls or a future `--all-certs` mode.

---

## LLM provider setup

All 17 tools work without an LLM (Large Language Model — the AI component that
generates plain-English summaries). Narration is the only LLM-dependent feature.
Every tool has a deterministic fallback that returns the same structured data in
a less polished format.

Set `UTILITY_LLM_PROVIDER` to enable narration. The AI narrates the output; it
never receives your KUBECONFIG or cluster tokens.

| Provider | Set this variable | Also required |
|---|---|---|
| Anthropic (Claude) | `UTILITY_LLM_PROVIDER=anthropic` | `ANTHROPIC_API_KEY` |
| OpenAI (GPT-4) | `UTILITY_LLM_PROVIDER=openai` | `OPENAI_API_KEY` |
| Vertex AI (Google) | `UTILITY_LLM_PROVIDER=vertex` | GCP Application Default Credentials or `GOOGLE_APPLICATION_CREDENTIALS` |
| Ollama (local, private) | `UTILITY_LLM_PROVIDER=ollama` | `OLLAMA_HOST` (default `http://localhost:11434`) |
| Disabled | unset or `UTILITY_LLM_PROVIDER=disabled` | nothing |

Verify narration is working:

```bash
UTILITY_LLM_PROVIDER=anthropic mcp-k8s-utility llm-probe
# Expected output: "narrated" and a short test response from the model
```

If you prefer complete data privacy and do not want any data leaving your network,
use `ollama` with a local model. The tool is tested against `llama3:8b` and
`mistral:7b`.

---

## RBAC and production install

RBAC (Role-Based Access Control) is how Kubernetes decides who can do what. A
ClusterRole is a bundle of permissions that you grant to a ServiceAccount (the
identity a running process uses to talk to the Kubernetes API). This section
explains exactly what permissions mcp-k8s-utility needs and why each one exists.

### Principle of least privilege

If you want to harden the installation, you can split the single ClusterRole in
`deploy/rbac.yaml` into two separate ClusterRoles:

- **Read-only ClusterRole** — grants `get`, `list`, and `watch` on all resources.
  Bind this to the ServiceAccount used by the diagnostic tools (1–13 minus
  execute paths). Anyone on the team can use this safely.

- **Privileged ClusterRole** — grants `create` and `delete` on Pods and
  `pods/exec`, plus `patch` on Certificates. Bind this only to the ServiceAccount
  used for control-plane rotation (Tools 14–17) and cert execution (Tool 3). This
  ServiceAccount should require separate approval to use.

For most teams running this in a trusted environment, the single ClusterRole below
is fine. For regulated environments, split it.

### Install the RBAC manifest

```bash
kubectl apply -f deploy/rbac.yaml
```

### What each permission does and why we need it

```yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: mcp-k8s-utility
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: mcp-k8s-utility
rules:
  # Read cluster state — used by all diagnostic tools
  - apiGroups: [""]
    resources: ["nodes", "namespaces", "pods", "services", "events", "configmaps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["cert-manager.io"]
    resources: ["certificates", "issuers", "clusterissuers"]
    verbs: ["get", "list", "watch", "patch"]

  # Pod deletion for cleanup_evicted_pods tool
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["delete"]

  # Privileged Pod creation for control-plane rotation probes and executor
  # Scoped to kube-system via the ClusterRoleBinding below; resourceNames is
  # intentionally empty (Pods are generateName-based and names are unknown
  # at policy-time — the namespace binding is the security boundary).
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["create"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: mcp-k8s-utility
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: mcp-k8s-utility
subjects:
  - kind: ServiceAccount
    name: mcp-k8s-utility
    namespace: kube-system
```

**Why we need each permission:**

| Permission | Resource | Why it is needed |
|---|---|---|
| `get`, `list`, `watch` | `nodes` | Tool 14–16: identify control-plane nodes; Tool 4: correlate node capacity with workload usage |
| `get`, `list`, `watch` | `pods` | Tools 5–7: find evicted Pods; Tools 14–16: check probe Pod status |
| `get`, `list`, `watch` | `events` | Tool 13: collect cluster events for postmortem |
| `get`, `list`, `watch` | `deployments`, `replicasets`, etc. | Tool 2: find dependent Deployments; Tool 4: right-sizing by workload |
| `get`, `list`, `watch`, `patch` | `certificates` (cert-manager) | Tool 1: list expiring certs; Tool 3: patch the force-renew annotation |
| `delete` | `pods` | Tool 7: delete evicted Pods from the cleanup plan |
| `create` | `pods` | Tools 14–16: create the short-lived privileged probe/executor Pod on master nodes |
| `create` | `pods/exec` | Tools 14–16: run `openssl` and rotation commands inside the probe Pod |

**On RBAC privilege elevation:** RBAC privilege elevation happens when a principal
(a user or ServiceAccount) can grant itself more permissions than it currently has.
mcp-k8s-utility does not have `bind`, `escalate`, or `impersonate` verbs, so it
cannot escalate its own privileges. The `pods/exec` permission does allow running
arbitrary commands inside privileged Pods — this is intentional for the control-
plane rotation use case but should be scoped carefully in regulated environments
(see the least-privilege split above).

---

## Environment variables reference

Variables are grouped by the part of the system they configure. If a variable is
not set, the tool either falls back to a safe default or degrades gracefully (the
feature is disabled, not the whole tool).

### Cluster access

| Variable | Default | What it does | If not set |
|---|---|---|---|
| `KUBECONFIG` | `~/.kube/config` | Path to your Kubernetes credentials file. All 17 tools use this to authenticate to the cluster. | Uses the default kubeconfig location. If that file does not exist, all Kubernetes calls fail. |

### Observability connections

| Variable | Default | What it does | If not set |
|---|---|---|---|
| `PROMETHEUS_URL` | — | Full URL to your Prometheus instance (e.g. `http://prometheus:9090`). Required by Tools 4, 8, 9, and 13. | Tools 4, 8, 9 return empty results. Tool 13 omits the metrics section. |
| `PROMETHEUS_BEARER_TOKEN` | — | Bearer token for Prometheus authentication. Use this or basic auth, not both. | No auth header is sent. Fine for clusters where Prometheus is open internally. |
| `PROMETHEUS_USER` | — | Username for Prometheus basic auth. | No basic auth is used. |
| `PROMETHEUS_PASSWORD` | — | Password for Prometheus basic auth. | No basic auth is used. |
| `OPENSEARCH_URL` | — | Full URL to your OpenSearch instance (e.g. `http://opensearch:9200`). Required by Tools 10, 11, 12, and 13. | Tools 10, 11, 12 return empty results. Tool 13 omits the log section. |
| `OPENSEARCH_USER` | — | Username for OpenSearch basic auth. | No basic auth is used. |
| `OPENSEARCH_PASSWORD` | — | Password for OpenSearch basic auth. | No basic auth is used. |
| `OPENSEARCH_API_KEY` | — | API key for OpenSearch authentication (alternative to user/password). | No API key auth is used. |

### LLM narration

| Variable | Default | What it does | If not set |
|---|---|---|---|
| `UTILITY_LLM_PROVIDER` | `disabled` | Which LLM provider to use for plain-English narration. Options: `anthropic`, `openai`, `vertex`, `ollama`, `disabled`. | Narration is disabled. All tools still work; output is structured data only. |
| `UTILITY_LLM_MODEL` | provider default | Override the specific model name within the provider (e.g. `claude-opus-4-5`). | Uses the provider's default model. |
| `ANTHROPIC_API_KEY` | — | API key for Anthropic. Required when `UTILITY_LLM_PROVIDER=anthropic`. | Narration fails with an authentication error. |
| `OPENAI_API_KEY` | — | API key for OpenAI. Required when `UTILITY_LLM_PROVIDER=openai`. | Narration fails with an authentication error. |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Path to a GCP service account JSON file. Required when `UTILITY_LLM_PROVIDER=vertex` without GCP Application Default Credentials. | Falls back to GCP ADC; fails if ADC is also not configured. |
| `OLLAMA_HOST` | `http://localhost:11434` | URL of your local Ollama server. Used when `UTILITY_LLM_PROVIDER=ollama`. | Uses the default localhost address. |

### Safety gates

| Variable | Default | What it does | If not set |
|---|---|---|---|
| `UTILITY_BUSINESS_HOURS_START_UTC` | `13` | UTC hour at which the business-hours block starts. Execute tools refuse to run after this hour. | Block starts at 13:00 UTC. |
| `UTILITY_BUSINESS_HOURS_END_UTC` | `21` | UTC hour at which the business-hours block ends. | Block ends at 21:00 UTC. |
| `UTILITY_BUSINESS_HOURS_DAYS` | `0,1,2,3,4` | Which weekdays the block applies to, as comma-separated numbers (0=Monday, 6=Sunday). | Block applies Monday–Friday. |
| `UTILITY_CLEANUP_NAMESPACE_ALLOWLIST` | — | Comma-separated list of namespace names where cleanup is allowed (e.g. `staging,dev,qa`). If set, no namespace outside this list will ever have Pods deleted. | All namespaces are candidates (subject to age gate and rate limit). |
| `UTILITY_MAX_RETENTION_DELETES` | `50` | Maximum number of OpenSearch indices deleted in a single execute_retention_cleanup call. A safety cap against runaway bulk deletes. | At most 50 indices are deleted per call. |

### Audit

| Variable | Default | What it does | If not set |
|---|---|---|---|
| `SECUREOPS_AUDIT_DB` | `~/.local/share/mcp-k8s-utility/audit.db` | Path to the SQLite audit ledger. Every action taken by an execute tool is recorded here with a cryptographic chain so tampering is detectable. | A new ledger is created at the default path on first use. |

---

## Troubleshooting

### "pip install fails with 'No matching distribution found'"

This usually means you are using Python 3.10 or older. mcp-k8s-utility requires
Python 3.11 or newer.

**Fix:** `python3.11 -m pip install 'mcp-k8s-utility==0.5.0'`. If you do not have
Python 3.11, install it with `brew install python@3.11` on macOS.

---

### "Claude Desktop doesn't show 17 tools" or "hammer icon is missing"

The MCP server did not start, or Claude did not pick up the config change.

**Fix:**
1. Quit Claude Desktop completely from the menu bar (not just close the window).
2. Open a terminal and run `mcp-k8s-utility serve-mcp` manually. If it exits
   with an error, the problem is in your install — fix that first.
3. Restart Claude Desktop and check the context panel on the left.
4. If the server starts but Claude still does not show the tools, check the logs:
   `~/Library/Logs/Claude/mcp-server-mcp-k8s-utility.log`

---

### "Tools return empty results even though the cluster is running"

The tool connected to Kubernetes successfully but found nothing, or could not
reach Prometheus/OpenSearch.

**For cert tools:** Check that cert-manager is installed:
```bash
kubectl get crd certificates.cert-manager.io
kubectl get certificates -A
```

**For Prometheus tools:** Check that `PROMETHEUS_URL` is set and reachable:
```bash
echo $PROMETHEUS_URL
curl -s "${PROMETHEUS_URL}/api/v1/query?query=up"
```

**For OpenSearch tools:** Check that `OPENSEARCH_URL` is set and reachable:
```bash
echo $OPENSEARCH_URL
curl -s "${OPENSEARCH_URL}/_cat/indices"
```

---

### "Control-plane tools return 'refused_unsupported_cluster_type' but I'm on kubeadm"

The cluster-type detection is looking at node annotations. k3s sets a
`k3s.io/node-args` annotation on its nodes; cloud providers set their own markers.
If you are running kubeadm but the tool refuses, check what your nodes look like:

```bash
kubectl get nodes -o json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for n in data['items']:
    print(n['metadata']['name'])
    print('  labels:', list(n['metadata'].get('labels', {}).keys())[:5])
    print('  annotations:', list(n['metadata'].get('annotations', {}).keys())[:5])
"
```

If you see `k3s.io/node-args` or cloud-provider annotations on your kubeadm nodes,
something in your cluster setup is adding them unexpectedly. Open an issue with the
output.

---

### "Executor Pod is stuck in Pending during control-plane rotation"

The privileged Pod cannot be scheduled. PodSecurityAdmission (the safety check
built into newer Kubernetes versions that blocks risky Pods from being created in
sensitive namespaces) may be rejecting it.

**Fix:**
1. Check events in kube-system:
   ```bash
   kubectl -n kube-system get events --sort-by='.lastTimestamp' | tail -20
   ```
2. Look for messages like "pods violates PodSecurity" or "admission webhook denied."
3. If PodSecurityAdmission is the cause, label the `kube-system` namespace to allow
   privileged Pods (this is the standard configuration for kubeadm clusters):
   ```bash
   kubectl label namespace kube-system \
     pod-security.kubernetes.io/enforce=privileged \
     --overwrite
   ```
4. If an admission webhook is blocking it, check which webhooks are active:
   ```bash
   kubectl get validatingwebhookconfigurations
   ```

---

### "execute_certificate_renewal refused — business hours"

The tool's business-hours gate is blocking execution. This is correct behaviour —
certificate renewals that restart Deployments carry risk and should not run during
peak traffic hours.

**Options:**
- Wait until after 21:00 UTC and try again.
- Pass `force=true` if you have an urgent expiry and accept the risk.
- Change the business-hours window with the `UTILITY_BUSINESS_HOURS_*` environment
  variables (see [Environment variables reference](#environment-variables-reference)).

---

### "draft_postmortem output has no metrics or logs"

Prometheus and/or OpenSearch were not reachable when the tool ran.

**Fix:** Check that `PROMETHEUS_URL` and `OPENSEARCH_URL` are exported in the same
shell (or set in Claude Desktop's `env` block) and that both services are reachable
from your machine. The tool renders a valid document even when both are missing —
the metrics and logs sections will note "unavailable."

---

## Architecture

How the pieces fit together, from a user typing a question to a Kubernetes API call
and back.

```
1. You type a question in Claude Desktop (or any MCP-compatible AI host)

2. The AI decides which tool(s) to call and with what arguments
   (It NEVER calls Kubernetes directly — it only calls the tools)
         │
         │  MCP stdio transport (local process on your machine)
         ▼
3. mcp_server.py — 17 @mcp.tool handlers (FastMCP)
         │
         ├── Kubernetes API  (kubernetes-asyncio, authenticated via KUBECONFIG)
         │     - all tools: read (list pods, certs, nodes, events)
         │     - Tool 3: patch cert annotation
         │     - Tools 5-7: delete evicted pods
         │     - Tools 14-16: create/exec/delete privileged probe pods
         │
         ├── Prometheus HTTP API  (PROMETHEUS_URL)
         │     - Tool 4: CPU/memory usage for right-sizing
         │     - Tools 8-9: alert flap rates
         │     - Tool 13: point-in-time metrics for postmortem
         │
         ├── OpenSearch HTTP API  (OPENSEARCH_URL)
         │     - Tools 10-12: index listing and deletion
         │     - Tool 13: log counts for postmortem
         │
         ├── LLM provider  (UTILITY_LLM_PROVIDER)
         │     - narration only: receives structured data, returns plain English
         │     - NEVER receives kubeconfig, tokens, or credentials
         │
         └── mcp-k8s-secure-ops broker  (sidecar or in-process)
               OPA policy check → short-lived token → audit row
               used by: execute_certificate_renewal (dependent rollout step)
         │
         ▼
4. The tool returns structured data (JSON) to the AI

5. The AI narrates the result in plain English and displays it to you
```

**The trust boundary:** The AI is a narrator, not an actor. It receives the
structured output of each tool call — a list of certificates, a cleanup plan, a
rotation result — and explains it to you. It never sees your KUBECONFIG, never
holds a Kubernetes token, and never talks to the Kubernetes API directly. The tool
layer is the adapter between the AI's world and your cluster. Every destructive
write goes through either Kubernetes RBAC (using the ServiceAccount from
`deploy/rbac.yaml`) or the `mcp-k8s-secure-ops` broker (which adds an OPA policy
check and an audit row before allowing the action).

---

Apache-2.0. Maintainer: vellankikoti@gmail.com
