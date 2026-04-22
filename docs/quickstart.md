# mcp-k8s-utility — Quickstart

## Requirements

- **macOS** (arm64 or amd64) or **Linux**
- **Python 3.11+** (`python3.13` recommended; `python3` on macOS Ventura ships 3.9 which won't install the wheel)
- **Docker Desktop** (running)
- **kind** 0.20+
- **kubectl** 1.28+
- **helm** 3.13+
- **uv** — <https://docs.astral.sh/uv/>

Check all at once:

```bash
for c in python3.13 docker kind kubectl helm uv; do
  command -v "$c" && "$c" --version 2>/dev/null | head -1 || echo "MISSING: $c"
done
```

Install guides: [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation) · [kubectl](https://kubernetes.io/docs/tasks/tools/) · [helm](https://helm.sh/docs/intro/install/) · [uv](https://docs.astral.sh/uv/getting-started/installation/)

## 3-command quickstart

```bash
git clone https://github.com/vellankikoti/mcp-k8s-utility
cd mcp-k8s-utility
make demo
```

`make demo` runs `tests/demo/demo-up.sh`, which:

1. Creates a `kind` cluster named `utility-demo`
2. Installs **cert-manager** (self-signed issuer for certificate scenarios)
3. Installs **Prometheus-lite** (no alertmanager, no pushgateway — keeps install under 2 min)
4. Creates `demo-staging` and `demo-prod` (tier=prod) namespaces
5. Seeds a `payments-tls` Certificate in demo-prod (48h TTL — already within a 14-day expiry window)
6. Deploys `checkout` (3 replicas, 500m CPU / 512Mi memory requests) in demo-prod for right-sizing
7. Seeds an Evicted pod in demo-staging for cleanup scenario

First run takes 3–5 minutes (Docker image pulls). Subsequent runs are faster.

## After `make demo` finishes

### 1. Port-forward Prometheus

```bash
kubectl port-forward -n monitoring svc/prometheus-server 9090:80 &
```

### 2. Wire Claude Desktop

Copy the JSON snippet printed at the end of `make demo` into:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Then fully quit and reopen Claude Desktop (`Cmd+Q` → reopen). The `utility` server should appear in the tool list within a few seconds.

For full documentation on the config and all environment variables, see [docs/claude-desktop-config.md](claude-desktop-config.md).

### 3. Try the three demo scenarios

In Claude Desktop, try these prompts one at a time:

| Scenario | Prompt |
|---|---|
| A — Cert renewal | "List certificates expiring in the next 14 days in demo-prod, then propose a safe renewal plan." |
| B — Evicted pod cleanup | "Show me any evicted pods in demo-staging and propose a cleanup plan." |
| C — Postmortem | "We had a minor incident in demo-prod in the last 30 minutes. Draft a postmortem in Google-SRE style." |

Each scenario has a rehearsal cheat-sheet with expected tool calls and CLI verification steps:

```bash
bash tests/demo/scenario_a_cert_renewal.sh
bash tests/demo/scenario_b_evicted_pods.sh
bash tests/demo/scenario_c_draft_postmortem.sh

# Or run all three:
make demo-scenarios
```

### 4. Start the dashboard (optional)

```bash
make dashboard
# open http://localhost:8080
```

The dashboard shows 5 live tiles: cluster health, certificate expiry countdown, resource pressure, alert summary, and system health. Tiles degrade gracefully when a backend (Prometheus, OpenSearch) is not configured.

## Teardown

```bash
make demo-down
```

Deletes the `utility-demo` kind cluster and kills any lingering port-forwards.

## No cluster — try the CLI only

```bash
# Print version
uvx --python 3.13 mcp-k8s-utility version

# Probe the configured LLM provider (exits 1 with clean error if invalid)
UTILITY_LLM_PROVIDER=bogus uvx --python 3.13 mcp-k8s-utility llm-probe

# Start the dashboard (tiles show "unconfigured" without a cluster)
uvx --python 3.13 mcp-k8s-utility dashboard
```

## LLM provider setup (optional)

The tool works with any provider — or none. Pick whichever your organization already pays for:

```bash
# Vertex AI (Gemini)
export UTILITY_LLM_PROVIDER=vertex
export GOOGLE_CLOUD_PROJECT=your-project

# Anthropic (Claude)
export UTILITY_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (or any OpenAI-compatible gateway)
export UTILITY_LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
# export OPENAI_BASE_URL=https://your-corporate-gateway/v1   # optional

# Ollama (local)
export UTILITY_LLM_PROVIDER=ollama
export OLLAMA_HOST=http://localhost:11434

# No LLM at all (default for demo) — deterministic fallback on every narration
export UTILITY_LLM_PROVIDER=disabled
```

Every LLM call has a deterministic structured fallback. Safety guarantees (business-hours gating, dry-run enforcement, audit logging) are identical whether the LLM is enabled or not.

## Running the full CI gate locally

```bash
make gate
```

Runs: `ruff check` · `ruff format --check` · `mypy` · `pytest -v`

All 101 tests should pass before pushing a tag.
