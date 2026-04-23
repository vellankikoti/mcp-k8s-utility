#!/usr/bin/env bash
# scenario_d_control_plane_rotation.sh — cheat-sheet for the CP cert rotation demo
# Narrative only. The actual tool calls run through Claude Desktop (MCP).
# Prerequisites: demo-cp-up.sh has been run and the cluster is healthy.
set -euo pipefail

_bold() { printf '\033[1m%s\033[0m\n' "$*"; }
_step() { printf '\033[1;36m[STEP] %s\033[0m\n' "$*"; }
_ok()   { printf '\033[1;32m[ OK ] %s\033[0m\n' "$*"; }
_info() { printf '\033[0;37m%s\033[0m\n' "$*"; }

banner() {
  echo ""
  _bold "╔══════════════════════════════════════════════════════════════════════╗"
  _bold "║   Scenario D — Control-plane certificate rotation (mcp-k8s-utility) ║"
  _bold "╚══════════════════════════════════════════════════════════════════════╝"
  echo ""
}

cluster_check() {
  _step "1. Verify cluster is healthy (3 CPs + 1 worker)…"
  kubectl get nodes
  echo ""
}

show_cert_expiry_prompt() {
  _step "2. Ask Claude: check cert expiry on all masters"
  _info '  → In Claude Desktop, send:'
  echo '      "Check control plane certificate expiry across all masters."'
  echo ""
  _info '  Expected: Claude calls check_control_plane_cert_expiry → returns list of'
  _info '  ControlPlaneCertSummary with notAfter dates for apiserver, kubelet-client,'
  _info '  front-proxy-client, and etcd-server certs on each of the 3 masters.'
  echo ""
}

show_runbook_prompt() {
  _step "3. Ask Claude: generate rotation runbook for master-0"
  FIRST_CP=$(kubectl get nodes -l node-role.kubernetes.io/control-plane \
    --no-headers -o custom-columns=':metadata.name' | head -1)
  _info "  First control-plane node: ${FIRST_CP}"
  _info '  → In Claude Desktop, send:'
  echo "      \"Generate the cert rotation runbook for ${FIRST_CP}.\""
  echo ""
  _info '  Expected: Claude calls generate_control_plane_rotation_runbook → returns'
  _info '  14-step markdown runbook with pre-flight, commands, verification sections.'
  echo ""
}

show_dry_run_prompt() {
  _step "4. Ask Claude: dry-run the rotation (safe, no changes)"
  FIRST_CP=$(kubectl get nodes -l node-role.kubernetes.io/control-plane \
    --no-headers -o custom-columns=':metadata.name' | head -1)
  _info '  → In Claude Desktop, send:'
  echo "      \"Dry-run the control plane cert rotation on ${FIRST_CP}.\""
  echo ""
  _info '  Expected: Claude calls execute_control_plane_rotation with dry_run=True →'
  _info '  returns planned_dry_run status, 14 skipped_dry_run steps.'
  echo ""
}

show_real_rotation_prompt() {
  _step "5. Ask Claude: execute real rotation on ONE master (off-hours required)"
  FIRST_CP=$(kubectl get nodes -l node-role.kubernetes.io/control-plane \
    --no-headers -o custom-columns=':metadata.name' | head -1)
  _info "  NOTE: This spawns a privileged Pod on ${FIRST_CP} and runs all 14 steps."
  _info "  Only proceed if current UTC time is outside 13:00-21:00 on a weekday,"
  _info "  OR pass force_during_business_hours=True for demo purposes."
  _info '  → In Claude Desktop, send:'
  echo "      \"Execute the control plane cert rotation on ${FIRST_CP} (force outside business hours).\""
  echo ""
  _info '  Expected: Claude calls execute_control_plane_rotation with dry_run=False,'
  _info '  force_during_business_hours=True → status=completed, 14 executed steps.'
  echo ""
}

show_post_rotation_check() {
  _step "6. Verify cluster health after rotation"
  kubectl get nodes
  echo ""
  _info '  All nodes should be Ready. If the rotated master briefly shows NotReady'
  _info '  during kubelet restart, wait 30s and re-check.'
  echo ""
}

show_vault_bundle_prompt() {
  _step "7. Ask Claude: build Vault cert bundle from all masters"
  _info '  → In Claude Desktop, send:'
  echo '      "Build the Vault cert bundle from all control-plane nodes."'
  echo ""
  _info '  Expected: Claude calls build_vault_cert_bundle → returns VaultCertBundle'
  _info '  with 3 PEMs concatenated, base64 blob, and Vault ticket instructions.'
  echo ""
}

teardown_note() {
  _step "8. Teardown"
  echo "  kind delete cluster --name utility-cp-demo"
  echo ""
}

main() {
  banner
  cluster_check
  show_cert_expiry_prompt
  show_runbook_prompt
  show_dry_run_prompt
  show_real_rotation_prompt
  show_post_rotation_check
  show_vault_bundle_prompt
  teardown_note
  _ok "Scenario D cheat-sheet complete."
}

main "$@"
