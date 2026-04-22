# mcp-k8s-utility

**AI-assisted Kubernetes toil elimination** — cert renewal, right-sizing, cleanup, alert tuning, log retention, postmortem drafting. LLM-agnostic, policy-gated, audit-chained.

Capstone of the [mcp-k8s conference series](https://github.com/vellankikoti). Depends on `mcp-k8s-secure-ops` for every write it performs.

## Status

Pre-v0.1.0 — under active development.

## The safety invariants

1. The LLM never holds cluster credentials.
2. The LLM never decides a write — OPA + Kyverno + 5-min per-action tokens do.
3. Every tool call produces a cryptographically chained audit row.
4. Works with any LLM provider (Vertex, Anthropic, OpenAI, Ollama) — or none.

See [`VISION.md`](VISION.md) and [`PLAN.md`](PLAN.md) for the full design.

## License

Apache-2.0.
