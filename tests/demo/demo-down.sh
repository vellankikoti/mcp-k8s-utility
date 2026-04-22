#!/usr/bin/env bash
# demo-down.sh — idempotent teardown of the mcp-k8s-utility demo environment
# Usage: bash tests/demo/demo-down.sh   (or make demo-down)
set -euo pipefail

CLUSTER_NAME="utility-demo"

_step() { printf '\033[1;36m[STEP] %s\033[0m\n' "$*"; }
_ok()   { printf '\033[1;32m[ OK ] %s\033[0m\n' "$*"; }

_step "Deleting kind cluster '${CLUSTER_NAME}'…"
kind delete cluster --name "${CLUSTER_NAME}" 2>/dev/null || true
_ok "Cluster torn down."

_step "Killing any lingering port-forwards…"
pkill -f "kubectl port-forward" 2>/dev/null || true
_ok "port-forwards cleared."
