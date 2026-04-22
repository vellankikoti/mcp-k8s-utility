#!/usr/bin/env bash
# scenario_a_cert_renewal.sh — rehearsal cheat-sheet for Scenario A
# The ACTUAL demo runs through Claude Desktop (MCP). This script is the fallback CLI guide.
# Usage: bash tests/demo/scenario_a_cert_renewal.sh   (or make demo-scenarios)
set -euo pipefail

cat <<'BANNER'
╔══════════════════════════════════════════════════════════╗
║   Scenario A — cert renewal (demo-prod, business hours) ║
╚══════════════════════════════════════════════════════════╝

▶ CLAUDE DESKTOP PROMPT:
  "List certificates expiring in the next 14 days in demo-prod, then propose a
   safe renewal plan for them."

── PRE-CHECK ─────────────────────────────────────────────────
BANNER

kubectl -n demo-prod get certificate 2>/dev/null \
  || echo "(cert-manager not running or demo-prod namespace missing — run 'make demo' first)"
echo ""

cat <<'BODY'
── EXPECTED CLAUDE TOOL CALLS ──────────────────────────────
  1. list_expiring_certificates(within_days=14, namespace="demo-prod")
       → returns [payments-tls]
         (duration 48h, renewBefore 24h → already within 14-day window)

  2. propose_certificate_renewal(within_days=14, force_during_business_hours=false)
       → RenewalPlan with 1 step:
           certificate:       payments-tls
           annotation_patch:  {metadata.annotations.cert-manager.io/force-renew-at: <iso>}
           dependent_rollouts: [Deployment/checkout]  (mounts payments-tls-sec)

  3. (optional) execute_certificate_renewal(plan=<above>, dry_run=true)
       → All steps return status="skipped_dry_run"; nothing written to cluster.

── SAFETY STORY ────────────────────────────────────────────
  Try during UTC business hours (Mon–Fri 13:00–21:00 UTC):
    execute_certificate_renewal(plan=<above>, dry_run=false)
    → refused=true
      refusal_reason="Renewal refused: business hours (UTC 13:00–21:00 Mon-Fri)…"

  The tool NEVER annotates a Certificate during business hours unless
  force_during_business_hours=true. Every refusal is written to the
  tamper-evident secure-ops audit ledger.

── VERIFY AFTER CLAUDE RESPONDS ────────────────────────────
  # Check whether the force-renew annotation was applied:
  kubectl -n demo-prod get certificate payments-tls -o yaml \
    | grep -A2 "annotations:"

  # Review audit entry (if secure-ops audit DB is configured):
  sqlite3 "${SECUREOPS_AUDIT_DB:-~/.secureops/audit.db}" \
    'SELECT row_id, json_extract(payload_json,"$.proposal.tool_name"),
             json_extract(payload_json,"$.result.status")
     FROM audit_rows ORDER BY row_id DESC LIMIT 5' 2>/dev/null \
    || echo "(SECUREOPS_AUDIT_DB not set — secure-ops broker skipped for this run)"
BODY
echo ""
