# RBAC for mcp-k8s-utility

`deploy/rbac.yaml` creates a ServiceAccount, ClusterRole, and ClusterRoleBinding
that cover the minimum permissions the server needs. Apply it with:

```bash
kubectl apply -f deploy/rbac.yaml
```

## What each permission is used for

| Resource | Verbs | Used by |
|---|---|---|
| nodes, namespaces, pods, services, events, configmaps | get, list, watch | All diagnostic tools (list nodes, gather events for postmortem, etc.) |
| deployments, replicasets, statefulsets, daemonsets | get, list, watch | `propose_right_size_plan`, `propose_certificate_renewal` (dependent-workload scan) |
| certificates, issuers, clusterissuers | get, list, watch, patch | `list_expiring_certificates`, `execute_certificate_renewal` (patch adds the `force-renew-at` annotation) |
| pods — delete | delete | `execute_cleanup_plan` (removes evicted pods) |
| pods — create | create | Control-plane rotation tools: creates short-lived probe Pods (read-only, ~60s) and executor Pods (privileged, ~90s) in kube-system |
| pods/exec | create | Control-plane rotation tools: runs `openssl`, `kubeadm certs renew`, etc. inside the probe/executor Pod via kubectl exec |

## Why `pods/exec` is required for control-plane rotation

The rotation tools work by:
1. Creating a privileged Pod on the target master node with the host filesystem
   mounted at `/host`.
2. Running `kubectl exec` into that Pod to `chroot /host` and invoke `kubeadm`,
   `openssl`, and `systemctl` — all on the host, not in the container.

This means the ServiceAccount needs both `pods/create` and `pods/exec`. There is
no kubeadm-native remote API; exec into a privileged Pod is the standard
approach used by tools like `kube-bench` and `sonobuoy`.

The executor Pod runs for at most 3600 seconds and is always deleted in a
`finally` block — even on failure.

## How to harden: split into two ServiceAccounts

The default setup uses one ServiceAccount for everything. For production, split it:

**SA 1 — read-only diagnostics** (handles 13 of the 17 tools):
```yaml
rules:
  - apiGroups: [""]
    resources: ["nodes", "namespaces", "pods", "services", "events", "configmaps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["cert-manager.io"]
    resources: ["certificates", "issuers", "clusterissuers"]
    verbs: ["get", "list", "watch"]
```

**SA 2 — write operations** (cert renewal, cleanup, CP rotation):
```yaml
rules:
  - apiGroups: ["cert-manager.io"]
    resources: ["certificates"]
    verbs: ["patch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["delete", "create"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]
```

Mount SA 2 only when running with write operations enabled (or mount via Projected
volumes with short-lived tokens for the write SA).

## How to scope CP rotation to kube-system only

The ClusterRoleBinding gives cluster-wide pod create/exec. To restrict CP rotation
to kube-system only, replace the ClusterRoleBinding with a RoleBinding:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: mcp-k8s-utility-cp-rotation
  namespace: kube-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: mcp-k8s-utility-cp-write
subjects:
  - kind: ServiceAccount
    name: mcp-k8s-utility
    namespace: kube-system
```

Then use a separate ClusterRoleBinding (without `pods/create` and `pods/exec`) for
the read-only permissions that must work across all namespaces.

## Auditing via the audit ledger

Every tool call that goes through the `mcp-k8s-secure-ops` broker creates an audit
row in the SQLite ledger at `~/.local/share/mcp-k8s-secure-ops/audit.db`. To query
recent write operations:

```bash
sqlite3 ~/.local/share/mcp-k8s-secure-ops/audit.db \
  "SELECT created_at, tool, action_id, status FROM audit_log ORDER BY created_at DESC LIMIT 20;"
```

The dashboard (`mcp-k8s-utility dashboard`) also surfaces recent audit rows at
`http://localhost:8080`.

## k3s / k3d note

On k3s/k3d clusters, the four control-plane rotation tools (`check_control_plane_cert_expiry`,
`generate_control_plane_rotation_runbook`, `execute_control_plane_rotation`,
`build_vault_cert_bundle`) will immediately return a structured refusal — they do not
create any Pods and do not need `pods/create` or `pods/exec` on k3s. You can strip
those permissions from the ClusterRole when deploying to k3s clusters.
