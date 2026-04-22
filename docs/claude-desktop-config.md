# Claude Desktop — MCP server wiring

This project exposes its 13 tools via the Model Context Protocol over stdio.
Claude Desktop picks them up by reading `~/Library/Application Support/Claude/claude_desktop_config.json`.

## Minimal config — `mcp-k8s-utility` only

```json
{
  "mcpServers": {
    "utility": {
      "command": "uv",
      "args": ["run", "--project", "/absolute/path/to/mcp-k8s-utility", "mcp-k8s-utility", "serve-mcp"],
      "env": {
        "KUBECONFIG": "/Users/YOU/.kube/config",
        "UTILITY_LLM_PROVIDER": "disabled"
      }
    }
  }
}
```

Replace `/absolute/path/to/mcp-k8s-utility` with the actual path printed by `make demo` at the end of bootstrap (or run `pwd` inside the cloned repo).

## Full config — both servers wired

When running the full demo (cert renewal goes through the secure-ops broker for policy enforcement + audit logging), wire both servers:

```json
{
  "mcpServers": {
    "utility": {
      "command": "uv",
      "args": ["run", "--project", "/absolute/path/to/mcp-k8s-utility", "mcp-k8s-utility", "serve-mcp"],
      "env": {
        "KUBECONFIG": "/Users/YOU/.kube/config",
        "PROMETHEUS_URL": "http://localhost:9090",
        "OPENSEARCH_URL": "",
        "SECUREOPS_AUDIT_DB": "/Users/YOU/.secureops/audit.db",
        "UTILITY_LLM_PROVIDER": "disabled"
      }
    },
    "secureops": {
      "command": "uvx",
      "args": ["mcp-k8s-secure-ops", "serve-mcp"],
      "env": {
        "KUBECONFIG": "/Users/YOU/.kube/config",
        "SECUREOPS_OPA_URL": "http://localhost:8181",
        "SECUREOPS_AUDIT_DB": "/Users/YOU/.secureops/audit.db"
      }
    }
  }
}
```

## Environment variables

| Variable | Purpose |
|---|---|
| `KUBECONFIG` | Kubernetes cluster to operate against. Points to your `~/.kube/config` or a per-cluster kubeconfig file. |
| `PROMETHEUS_URL` | Base URL of the Prometheus server (used by right-sizing, alert-tuning, and postmortem tools). Leave empty or omit to disable — tools degrade gracefully. |
| `OPENSEARCH_URL` | Base URL of OpenSearch (used by log-retention cleanup and postmortem log correlation). Leave empty or omit to disable. |
| `SECUREOPS_AUDIT_DB` | Absolute path to the secure-ops SQLite audit ledger. Tools read recent audit rows for postmortem correlation. Leave empty to disable. |
| `UTILITY_LLM_PROVIDER` | One of `vertex`, `anthropic`, `openai`, `ollama`, `disabled`. `disabled` returns a deterministic structured fallback on every narration call. No external calls made. |
| `UTILITY_LLM_MODEL` | Override the model name for the chosen provider (optional). Each provider has a sensible default. |
| `ANTHROPIC_API_KEY` | Required when `UTILITY_LLM_PROVIDER=anthropic`. |
| `OPENAI_API_KEY` | Required when `UTILITY_LLM_PROVIDER=openai`. |
| `OPENAI_BASE_URL` | Override the OpenAI-compatible endpoint (optional). Useful for corporate gateways. |
| `GOOGLE_CLOUD_PROJECT` | Required when `UTILITY_LLM_PROVIDER=vertex`. |
| `OLLAMA_HOST` | Override the Ollama base URL (default `http://localhost:11434`). Required when `UTILITY_LLM_PROVIDER=ollama`. |
| `UTILITY_CLEANUP_NAMESPACE_ALLOWLIST` | Comma-separated list of namespaces the cleanup tool is permitted to operate in. Empty = all namespaces allowed. |

## Port-forwarding Prometheus

The demo cluster runs Prometheus inside kind. Before using any metrics-backed tool, start the port-forward in a separate terminal:

```bash
kubectl port-forward -n monitoring svc/prometheus-server 9090:80
```

Set `PROMETHEUS_URL=http://localhost:9090` in the MCP config (already included in the snippet that `make demo` prints).

## Troubleshooting

**Claude Desktop doesn't see the `utility` server at all.**

- Fully quit Claude Desktop (`Cmd+Q`) and reopen. Config changes are read only at startup.
- Verify the JSON is valid — a trailing comma or unmatched brace silently disables all servers. Use `python3 -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json` to validate.
- Check `~/Library/Logs/Claude/mcp-server-utility.log` for Python import errors or missing executable errors.
- Run the server manually: `uv run --project /path/to/mcp-k8s-utility mcp-k8s-utility serve-mcp`. If it prints JSON-RPC on stdout without crashing, the binary is healthy (the JSON-RPC output on a terminal is expected — Claude speaks it, not you).

**The server appears in Claude but every tool call errors with "cluster unreachable".**

- Confirm `KUBECONFIG` points to a reachable cluster: `kubectl --kubeconfig=$KUBECONFIG get ns`.
- If using the demo cluster: `kind get clusters` should list `utility-demo`.
- Open the dashboard (`make dashboard`, then `http://localhost:8080`) and inspect the **System health** tile — it shows which backends are misconfigured.

**Cert-renewal tool refuses during business hours.**

That is intentional safety behavior. The tool blocks writes during UTC business hours (Mon–Fri 13:00–21:00 UTC) unless `force_during_business_hours=true` is passed. See `scenario_a_cert_renewal.sh` for details.

**MCP stdio JSON-RPC hangs when tested manually.**

FastMCP 3.x expects one JSON-RPC message per newline-delimited line on stdin. Do not use raw `echo` for manual testing. Use the Python harness from the Week 1 verification script or test via Claude Desktop directly.

**`uvx mcp-k8s-secure-ops` fails with "not found".**

Ensure `mcp-k8s-secure-ops>=1.0.3` is published on PyPI and your `uvx` version is current (`uv self update`). The package is a runtime dependency; `uvx` will pull it from PyPI the first time.
