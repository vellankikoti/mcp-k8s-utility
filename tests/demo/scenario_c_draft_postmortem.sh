#!/usr/bin/env bash
# scenario_c_draft_postmortem.sh — rehearsal cheat-sheet for Scenario C
# The ACTUAL demo runs through Claude Desktop (MCP). This script is the fallback CLI guide.
# Usage: bash tests/demo/scenario_c_draft_postmortem.sh   (or make demo-scenarios)
set -euo pipefail

cat <<'BANNER'
╔══════════════════════════════════════════════════════════╗
║   Scenario C — draft_postmortem (unexpected delight)     ║
╚══════════════════════════════════════════════════════════╝

▶ CLAUDE DESKTOP PROMPT:
  "We had a minor incident in demo-prod in the last 30 minutes.
   Draft a postmortem in Google-SRE style."

── CONTEXT ──────────────────────────────────────────────────
  The synthesis tool pulls correlated signals from multiple backends:
    - K8s events in the time window  (core_v1.list_namespaced_event)
    - Prometheus metrics             (error rate + p99 latency)
                                     "unavailable" if PROMETHEUS_URL not set
    - OpenSearch logs                (if OPENSEARCH_URL configured)
                                     "unconfigured" otherwise
    - Secure-ops audit rows in window (if SECUREOPS_AUDIT_DB configured)

▶ EXPECTED TOOL CALL:
  draft_postmortem(minutes_back=30, namespace="demo-prod", workload="checkout")

▶ EXPECTED OUTPUT SHAPE:
  {
    "window_start": "...",
    "window_end": "...",
    "sources": {
      "events": [...],
      "events_source": "k8s",
      "prometheus_samples": [
        {"name": "error_rate_5m", ...},
        {"name": "p99_latency_5m_ms", ...}
      ],
      "logs": {"total": 0, "buckets": [], "source": "unconfigured"},
      "audit": [...],
      "audit_source": "sqlite" | "unconfigured"
    },
    "markdown": "# Postmortem — checkout  (2026-...)\n\n...",
    "llm_narrated": false
  }

── THE DELIGHT ─────────────────────────────────────────────
  With UTILITY_LLM_PROVIDER=disabled (the demo default), the fallback
  renderer produces a valid Google-SRE postmortem skeleton directly from
  the structured signals — no LLM, no hallucination, always reproducible.

  When UTILITY_LLM_PROVIDER=anthropic|vertex|openai|ollama is set, the
  SAME structured data is sent to the LLM for a narrated 2-3-paragraph
  Root Cause + Action Items draft. The raw sources are ALWAYS present
  underneath the markdown so every claim can be verified.

── TRY IT LIVE ─────────────────────────────────────────────
  After Claude responds, copy the "markdown" field into a text editor.
  Compare against "sources.events" and "sources.prometheus_samples" for
  factual fidelity — confirm no detail in the narrative is unsupported
  by the raw signals.

── ENABLE LLM NARRATION (optional) ─────────────────────────
  Edit the Claude Desktop config to add/change:
    "UTILITY_LLM_PROVIDER": "anthropic",
    "ANTHROPIC_API_KEY": "sk-ant-..."
  Restart Claude Desktop, then re-run the same prompt.
  The markdown will be richer; sources remain unchanged.
BANNER
echo ""
