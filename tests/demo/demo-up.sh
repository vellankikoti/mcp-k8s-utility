#!/usr/bin/env bash
# demo-up.sh — bootstrap mcp-k8s-utility demo environment
# Idempotent: tears down previous cluster first, then rebuilds cleanly.
# Usage: bash tests/demo/demo-up.sh   (or make demo)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLUSTER_NAME="utility-demo"

_bold() { printf '\033[1m%s\033[0m\n' "$*"; }
_step() { printf '\033[1;36m[STEP] %s\033[0m\n' "$*"; }
_ok()   { printf '\033[1;32m[ OK ] %s\033[0m\n' "$*"; }
_warn() { printf '\033[1;33m[WARN] %s\033[0m\n' "$*"; }
_err()  { printf '\033[1;31m[ERR ] %s\033[0m\n' "$*" >&2; }

banner() {
  echo ""
  _bold "╔══════════════════════════════════════════════════════════╗"
  _bold "║   mcp-k8s-utility  ·  demo environment bootstrap        ║"
  _bold "╚══════════════════════════════════════════════════════════╝"
  echo ""
}

check_prereqs() {
  _step "Checking prerequisites…"
  local missing=0
  for cmd in kind kubectl helm docker uv; do
    if ! command -v "$cmd" &>/dev/null; then
      _err "Missing required tool: $cmd"
      missing=1
    else
      _ok "$cmd found"
    fi
  done
  if [[ $missing -eq 1 ]]; then
    echo ""
    echo "Install missing tools:"
    echo "  kind:    https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
    echo "  kubectl: https://kubernetes.io/docs/tasks/tools/"
    echo "  helm:    https://helm.sh/docs/intro/install/"
    echo "  docker:  https://docs.docker.com/engine/install/"
    echo "  uv:      https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
  fi
  if ! docker info &>/dev/null; then
    _err "Docker daemon is not running. Start Docker Desktop."
    exit 1
  fi
  _ok "Docker daemon reachable"
}

setup_cluster() {
  _step "Tearing down existing '${CLUSTER_NAME}' cluster (if any)…"
  kind delete cluster --name "${CLUSTER_NAME}" 2>/dev/null || true
  _step "Creating kind cluster '${CLUSTER_NAME}'…"
  kind create cluster --name "${CLUSTER_NAME}" --wait 120s
  _ok "kind cluster ready"
}

install_cert_manager() {
  _step "Installing cert-manager (demo uses self-signed issuer)…"
  helm repo add jetstack https://charts.jetstack.io --force-update 2>/dev/null || true
  helm repo update jetstack >/dev/null
  helm upgrade --install cert-manager jetstack/cert-manager \
    --namespace cert-manager --create-namespace \
    --set crds.enabled=true \
    --set global.leaderElection.namespace=cert-manager \
    --wait --timeout 300s
  _ok "cert-manager installed"
}

install_prometheus() {
  _step "Installing prometheus-community/prometheus (lite, no alertmanager/pushgateway)…"
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update 2>/dev/null || true
  helm repo update prometheus-community >/dev/null
  helm upgrade --install prometheus prometheus-community/prometheus \
    --namespace monitoring --create-namespace \
    --set alertmanager.enabled=false \
    --set pushgateway.enabled=false \
    --set prometheus-node-exporter.enabled=false \
    --set server.persistentVolume.enabled=false \
    --set prometheus-pushgateway.enabled=false \
    --wait --timeout 180s
  _ok "Prometheus installed"
  _ok "  Port-forward: kubectl port-forward -n monitoring svc/prometheus-server 9090:80"
}

create_namespaces() {
  _step "Creating demo namespaces…"
  kubectl create namespace demo-staging 2>/dev/null || true
  kubectl create namespace demo-prod    2>/dev/null || true
  kubectl label namespace demo-prod tier=prod --overwrite >/dev/null
  _ok "Namespaces: demo-staging (unlabeled), demo-prod (tier=prod)"
}

seed_cert_manager_resources() {
  _step "Seeding a self-signed Certificate in demo-prod (48h duration, renews after 24h)…"
  kubectl apply -f - <<'YAML'
apiVersion: cert-manager.io/v1
kind: Issuer
metadata:
  name: self-signed
  namespace: demo-prod
spec:
  selfSigned: {}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: payments-tls
  namespace: demo-prod
spec:
  secretName: payments-tls-sec
  duration: 48h
  renewBefore: 24h
  dnsNames:
    - payments.demo.local
  issuerRef:
    name: self-signed
    kind: Issuer
YAML
  _ok "Certificate 'payments-tls' created in demo-prod (48h TTL → already within 14d window)"
}

deploy_workloads() {
  _step "Deploying oversized 'checkout' workload in demo-prod (for right-sizing scenario)…"
  kubectl apply -f - <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: demo-prod
spec:
  replicas: 3
  selector: { matchLabels: { app: checkout } }
  template:
    metadata: { labels: { app: checkout } }
    spec:
      containers:
        - name: app
          image: nginx:1.27
          ports: [{ containerPort: 80 }]
          resources:
            requests: { cpu: 500m, memory: 512Mi }
            limits:   { cpu: 1,    memory: 1Gi }
          volumeMounts:
            - name: tls
              mountPath: /etc/tls
              readOnly: true
      volumes:
        - name: tls
          secret:
            secretName: payments-tls-sec
            optional: true
YAML
  kubectl -n demo-prod rollout status deploy/checkout --timeout=120s
  _ok "checkout (3 replicas, 500m/512Mi requests) rolled out in demo-prod"
}

seed_evicted_pod() {
  _step "Seeding a canonical Evicted pod in demo-staging…"
  # Apply a short-lived Pod, wait for completion, then patch status to Failed/Evicted.
  # This is a test-only technique — Pod has no owner (intentionally orphaned).
  kubectl apply -f - <<'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: stale-pod-1
  namespace: demo-staging
  labels: { demo: evicted-seed }
spec:
  restartPolicy: Never
  containers:
    - name: ghost
      image: busybox:1.36
      command: ["sh", "-c", "exit 0"]
YAML
  # Wait for Succeeded or Failed before touching status subresource
  kubectl -n demo-staging wait --for=jsonpath='{.status.phase}'=Succeeded \
    pod/stale-pod-1 --timeout=60s 2>/dev/null \
    || kubectl -n demo-staging wait --for=jsonpath='{.status.phase}'=Failed \
       pod/stale-pod-1 --timeout=30s 2>/dev/null || true
  # Patch status to mimic an Evicted pod
  if kubectl -n demo-staging patch pod stale-pod-1 \
       --type=merge --subresource=status \
       -p '{"status":{"phase":"Failed","reason":"Evicted","message":"The node was low on resource: ephemeral-storage."}}' \
       2>/dev/null; then
    _ok "stale-pod-1 patched to Failed/Evicted in demo-staging"
  else
    _warn "Could not patch pod status to Evicted — some kube-apiserver versions restrict this. Demo still works; list_evicted_pods will show 0 candidates."
  fi
}

emit_claude_config() {
  local kubeconfig="${HOME}/.kube/config"
  local audit_db="${HOME}/.secureops/audit.db"
  echo ""
  _bold "════════════════════════════════════════════════════════════"
  _bold " Claude Desktop MCP config — paste into:"
  _bold "   ${HOME}/Library/Application Support/Claude/claude_desktop_config.json"
  _bold "════════════════════════════════════════════════════════════"
  echo ""
  cat <<EOF
{
  "mcpServers": {
    "utility": {
      "command": "uv",
      "args": ["run", "--project", "${REPO_ROOT}", "mcp-k8s-utility", "serve-mcp"],
      "env": {
        "KUBECONFIG": "${kubeconfig}",
        "PROMETHEUS_URL": "http://localhost:9090",
        "SECUREOPS_AUDIT_DB": "${audit_db}",
        "UTILITY_LLM_PROVIDER": "disabled"
      }
    }
  }
}
EOF
  echo ""
  _bold "Next steps:"
  echo ""
  echo "  1. Port-forward Prometheus (second terminal):"
  echo "       kubectl port-forward -n monitoring svc/prometheus-server 9090:80 &"
  echo ""
  echo "  2. Paste the config above into Claude Desktop and restart Claude (Cmd+Q)."
  echo ""
  echo "  3. Run scenario cheat-sheets for rehearsal:"
  echo "       bash tests/demo/scenario_a_cert_renewal.sh"
  echo "       bash tests/demo/scenario_b_evicted_pods.sh"
  echo "       bash tests/demo/scenario_c_draft_postmortem.sh"
  echo ""
  echo "     Or run all three in sequence:"
  echo "       make demo-scenarios"
  echo ""
  echo "  4. Start the dashboard (separate terminal):"
  echo "       make dashboard"
  echo "       open http://localhost:8080"
  echo ""
  echo "  5. When done:"
  echo "       make demo-down"
  echo ""
}

main() {
  banner
  check_prereqs
  setup_cluster
  install_cert_manager
  install_prometheus
  create_namespaces
  seed_cert_manager_resources
  deploy_workloads
  seed_evicted_pod
  emit_claude_config
}

main "$@"
