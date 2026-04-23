#!/usr/bin/env bash
# demo-cp-up.sh — bootstrap the 3-control-plane kind cluster for scenario D
# (control-plane certificate rotation).
# Usage: bash tests/demo/demo-cp-up.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLUSTER_NAME="utility-cp-demo"
KIND_CONFIG="${REPO_ROOT}/tests/demo/cp-rotation-kind.yaml"

_bold() { printf '\033[1m%s\033[0m\n' "$*"; }
_step() { printf '\033[1;36m[STEP] %s\033[0m\n' "$*"; }
_ok()   { printf '\033[1;32m[ OK ] %s\033[0m\n' "$*"; }
_warn() { printf '\033[1;33m[WARN] %s\033[0m\n' "$*"; }
_err()  { printf '\033[1;31m[ERR ] %s\033[0m\n' "$*" >&2; }

banner() {
  echo ""
  _bold "╔══════════════════════════════════════════════════════════╗"
  _bold "║   mcp-k8s-utility  ·  3-CP kind cluster for scenario D  ║"
  _bold "╚══════════════════════════════════════════════════════════╝"
  echo ""
}

check_prereqs() {
  _step "Checking prerequisites…"
  local missing=0
  for cmd in kind kubectl docker; do
    if ! command -v "$cmd" &>/dev/null; then
      _err "Missing required tool: $cmd"
      missing=1
    else
      _ok "$cmd found"
    fi
  done
  if [[ $missing -eq 1 ]]; then exit 1; fi
  if ! docker info &>/dev/null; then
    _err "Docker daemon is not running."
    exit 1
  fi
  _ok "Docker daemon reachable"
  # Memory check: 3 control planes need >= 8 GiB Docker RAM
  local mem_bytes
  mem_bytes=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  local mem_gib=$(( mem_bytes / 1024 / 1024 / 1024 ))
  if [[ $mem_gib -lt 6 ]]; then
    _warn "Docker has only ~${mem_gib} GiB RAM. 3-CP cluster needs ≥ 6 GiB. May timeout."
  else
    _ok "Docker RAM: ~${mem_gib} GiB (sufficient)"
  fi
}

setup_cluster() {
  _step "Tearing down existing '${CLUSTER_NAME}' cluster (if any)…"
  kind delete cluster --name "${CLUSTER_NAME}" 2>/dev/null || true
  _step "Creating 3-control-plane kind cluster '${CLUSTER_NAME}'…"
  _warn "This takes ~3-5 minutes. Multi-CP clusters require kubeadm join on each node."
  kind create cluster --config "${KIND_CONFIG}" --wait 300s
  _ok "kind cluster '${CLUSTER_NAME}' ready"
}

verify_nodes() {
  _step "Verifying node topology…"
  kubectl get nodes -o wide
  local cp_count
  cp_count=$(kubectl get nodes -l node-role.kubernetes.io/control-plane --no-headers 2>/dev/null | wc -l | tr -d ' ')
  if [[ "${cp_count}" -ne 3 ]]; then
    _warn "Expected 3 control-plane nodes, got ${cp_count}"
  else
    _ok "3 control-plane nodes confirmed"
  fi
}

emit_config() {
  local kubeconfig="${HOME}/.kube/config"
  echo ""
  _bold "════════════════════════════════════════════════════════════"
  _bold " Claude Desktop MCP config for scenario D — paste into:"
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
        "UTILITY_LLM_PROVIDER": "disabled"
      }
    }
  }
}
EOF
  echo ""
  _bold "Next steps for scenario D:"
  echo "  1. Paste config into Claude Desktop and restart."
  echo "  2. Run the scenario cheat-sheet:"
  echo "       bash tests/demo/scenario_d_control_plane_rotation.sh"
  echo "  3. Or validate via the Python harness:"
  echo "       uv run python tests/demo/validate_cp_rotation.py"
  echo ""
  echo "  When done: kind delete cluster --name ${CLUSTER_NAME}"
  echo ""
}

main() {
  banner
  check_prereqs
  setup_cluster
  verify_nodes
  emit_config
}

main "$@"
