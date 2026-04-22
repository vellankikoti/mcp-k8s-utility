# mcp-k8s-utility

**AI-assisted Kubernetes toil elimination** — cert renewal, right-sizing, cleanup, alert tuning, log retention, postmortem drafting. LLM-agnostic, policy-gated, audit-chained.

Capstone of the [mcp-k8s conference series](https://github.com/vellankikoti). Depends on `mcp-k8s-secure-ops` for every write it performs.

## Status

v0.1.1 alpha — under active development.

## Requirements

- **Python 3.11 or newer** (macOS default `python3` is 3.9 — use `python3.11` or newer explicitly)
- Kubernetes cluster reachable via `$KUBECONFIG` (local `kind` is fine)
- (Optional) `mcp-k8s-secure-ops` broker deployed for policy-gated writes
- (Optional) Prometheus, cert-manager, OpenSearch, Grafana — only the tools you use need the corresponding sidecar.

## Install

```bash
# with uv (recommended)
uvx --python 3.11 mcp-k8s-utility version

# with pip
python3.11 -m venv .venv && source .venv/bin/activate
pip install mcp-k8s-utility
```

## The safety invariants

1. The LLM never holds cluster credentials.
2. The LLM never decides a write — OPA + Kyverno + 5-min per-action tokens do.
3. Every tool call produces a cryptographically chained audit row.
4. Works with any LLM provider (Vertex, Anthropic, OpenAI, Ollama) — or none.

See [`VISION.md`](VISION.md) and [`PLAN.md`](PLAN.md) for the full design.

## License

Apache-2.0.
