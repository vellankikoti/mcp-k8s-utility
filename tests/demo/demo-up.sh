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
  # Warn if other kind clusters are running — they consume Docker memory and can
  # cause kubeadm TLS timeouts on resource-constrained machines (< 12 GiB Docker RAM).
  local other_clusters
  other_clusters=$(kind get clusters 2>/dev/null | grep -v "^${CLUSTER_NAME}$" || true)
  if [[ -n "${other_clusters}" ]]; then
    _warn "Other kind clusters are running: $(echo "${other_clusters}" | tr '\n' ' ')"
    _warn "They consume Docker memory. If cluster creation times out, stop them first."
  fi
}

setup_cluster() {
  _step "Tearing down existing '${CLUSTER_NAME}' cluster (if any)…"
  kind delete cluster --name "${CLUSTER_NAME}" 2>/dev/null || true
  _step "Creating kind cluster '${CLUSTER_NAME}'…"
  # 300s wait to handle macOS Docker Desktop rate-limiter and resource contention
  kind create cluster --name "${CLUSTER_NAME}" --wait 300s
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
  _step "Installing prometheus-community/prometheus with synthetic flappy alert rules…"
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update 2>/dev/null || true
  helm repo update prometheus-community >/dev/null
  helm upgrade --install prometheus prometheus-community/prometheus \
    --namespace monitoring --create-namespace \
    -f "${REPO_ROOT}/tests/demo/prom-values.yaml" \
    --set alertmanager.enabled=false \
    --set pushgateway.enabled=false \
    --set prometheus-node-exporter.enabled=false \
    --set server.persistentVolume.enabled=false \
    --set prometheus-pushgateway.enabled=false \
    --wait --timeout 180s
  _ok "Prometheus installed (with demo-flaps rule group: DemoFlappyAlert + CriticalFlappyAlert)"
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
  # Use an unsatisfiable nodeAffinity so the pod stays Pending (no kubelet GC).
  # Then patch status to Failed/Evicted. The node-affinity approach is more robust
  # than ghost nodeName because Kubernetes GC does not clean up Pending pods with
  # unsatisfiable affinity the same way it cleans up pods with nonexistent nodeName.
  kubectl apply -f - <<'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: stale-pod-1
  namespace: demo-staging
  labels: { demo: evicted-seed }
spec:
  restartPolicy: Never
  terminationGracePeriodSeconds: 0
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: kubernetes.io/hostname
                operator: In
                values: ["ghost-node-that-never-exists"]
  containers:
    - name: ghost
      image: busybox:1.36
      command: ["sh", "-c", "sleep 1"]
YAML
  # Wait briefly for the Pod object to be created, then patch status.
  kubectl -n demo-staging wait --for=create pod/stale-pod-1 --timeout=15s >/dev/null 2>&1 || true
  if kubectl -n demo-staging patch pod stale-pod-1 --type=merge --subresource=status -p \
    '{"status":{"phase":"Failed","reason":"Evicted","message":"The node was low on resource: ephemeral-storage."}}' \
    >/dev/null 2>&1; then
    _ok "stale-pod-1 seeded Failed/Evicted (node-affinity technique — stays in Failed/Evicted state)"
  else
    _warn "status subresource patch rejected by kube-apiserver; scenario B will show 0 evicted pods"
  fi
}

start_opensearch() {
  _step "Starting local OpenSearch container…"
  docker rm -f secureops-opensearch 2>/dev/null || true
  docker run -d --name secureops-opensearch \
    -p 9200:9200 \
    -e "discovery.type=single-node" \
    -e "DISABLE_SECURITY_PLUGIN=true" \
    -e "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m" \
    opensearchproject/opensearch:2.11.1

  # Wait for OpenSearch to accept requests
  local retries=60
  while [[ $retries -gt 0 ]]; do
    if curl -sSf http://localhost:9200/_cluster/health >/dev/null 2>&1; then
      _ok "OpenSearch ready on :9200"
      break
    fi
    retries=$((retries - 1))
    sleep 2
  done
  if [[ $retries -eq 0 ]]; then
    _warn "OpenSearch didn't come up; scenario 5 will be skipped"
    return 0
  fi

  # Seed 3 old indices (names contain past dates so age_days will be computed correctly)
  _step "Seeding OpenSearch indices…"
  curl -sS -X PUT http://localhost:9200/logs-2025.12.01 -H 'content-type: application/json' -d '{
    "settings": {"number_of_shards": 1, "number_of_replicas": 0}
  }' >/dev/null
  curl -sS -X PUT http://localhost:9200/logs-2025.12.15 -H 'content-type: application/json' -d '{
    "settings": {"number_of_shards": 1, "number_of_replicas": 0}
  }' >/dev/null
  # Third index: tagged as compliance/retention via mapping _meta (scan.py checks mappings too)
  curl -sS -X PUT http://localhost:9200/logs-2026.01.01 -H 'content-type: application/json' -d '{
    "settings": {"number_of_shards": 1, "number_of_replicas": 0}
  }' >/dev/null
  # Set mapping _meta with retention tag on the third index
  curl -sS -X PUT "http://localhost:9200/logs-2026.01.01/_mapping" \
    -H 'content-type: application/json' \
    -d '{"_meta": {"retention": "compliance-2y"}}' >/dev/null

  # Populate each index with a few docs so store.size > 0
  for idx in logs-2025.12.01 logs-2025.12.15 logs-2026.01.01; do
    for i in 1 2 3 4 5; do
      curl -sS -X POST "http://localhost:9200/${idx}/_doc" \
        -H 'content-type: application/json' \
        -d "{\"msg\":\"test entry $i\",\"level\":\"error\",\"@timestamp\":\"2025-12-01T00:0${i}:00Z\"}" >/dev/null
    done
  done
  curl -sS -X POST http://localhost:9200/_refresh >/dev/null
  _ok "Seeded 3 indices (2 retention-eligible, 1 compliance-tagged via mapping _meta)"
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
  start_opensearch
  seed_evicted_pod
  emit_claude_config
}

main "$@"
