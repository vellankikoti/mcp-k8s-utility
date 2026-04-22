#!/usr/bin/env bash
# scenario_b_evicted_pods.sh — rehearsal cheat-sheet for Scenario B
# The ACTUAL demo runs through Claude Desktop (MCP). This script is the fallback CLI guide.
# Usage: bash tests/demo/scenario_b_evicted_pods.sh   (or make demo-scenarios)
set -euo pipefail

cat <<'BANNER'
╔══════════════════════════════════════════════════════════╗
║   Scenario B — cleanup evicted pods (demo-staging)       ║
╚══════════════════════════════════════════════════════════╝

▶ CLAUDE DESKTOP PROMPT:
  "Show me any evicted pods in demo-staging and propose a cleanup plan."

── PRE-CHECK ─────────────────────────────────────────────────
BANNER

kubectl -n demo-staging get pods -l demo=evicted-seed -o wide 2>/dev/null \
  || echo "(none matched — check that 'make demo' seeded the evicted pod)"
echo ""

cat <<'BODY'
── EXPECTED CLAUDE TOOL CALLS ──────────────────────────────
  1. list_evicted_pods(namespace="demo-staging")
       → [stale-pod-1]
         (phase=Failed, reason=Evicted, message="The node was low on resource: ephemeral-storage.")

  2. propose_cleanup_plan(namespace="demo-staging",
                          min_age_hours=0.0, max_deletes_per_namespace=20)
       → CleanupPlan with 1 candidate:
           pod:         stale-pod-1
           will_delete: true
           skip_reason: null

  3. (optional) execute_cleanup_plan(plan=<above>, dry_run=true)
       → Candidate: status="skipped_dry_run"; nothing deleted.

── SAFETY STORY ────────────────────────────────────────────
  * Phase filter:  only pods with phase=Failed AND reason=Evicted are candidates.
  * Age gate:      min_age_hours (default 1.0) rejects pods too recently evicted.
                   In this demo we pass 0.0 to include the freshly seeded pod.
  * Rate limit:    max 20 deletes per namespace per invocation (hard cap).
  * Namespace allowlist: UTILITY_CLEANUP_NAMESPACE_ALLOWLIST env var can restrict
                          which namespaces are eligible for cleanup.

── VERIFY ──────────────────────────────────────────────────
  # After a real (non-dry-run) execute_cleanup_plan:
  kubectl -n demo-staging get pods

  # Audit trail:
  sqlite3 "${SECUREOPS_AUDIT_DB:-~/.secureops/audit.db}" \
    'SELECT row_id, json_extract(payload_json,"$.proposal.tool_name"),
             json_extract(payload_json,"$.result.status")
     FROM audit_rows ORDER BY row_id DESC LIMIT 5' 2>/dev/null \
    || echo "(audit DB unset — secure-ops broker not in the loop for this demo)"
BODY
echo ""
