.PHONY: help demo demo-scenarios demo-down test gate dashboard clean install

help:
	@echo "mcp-k8s-utility — developer targets"
	@echo ""
	@echo "  make install        uv sync --all-extras"
	@echo "  make demo           bring up kind + cert-manager + prometheus + seed demo data"
	@echo "  make demo-scenarios run scenario cheat-sheets (requires 'make demo' first)"
	@echo "  make demo-down      tear down demo cluster"
	@echo "  make dashboard      start the HTTP dashboard on :8080"
	@echo "  make test           uv run pytest -v"
	@echo "  make gate           full local CI gate (ruff + mypy + pytest)"
	@echo "  make clean          remove .venv, caches, dist/"

install:
	uv sync --all-extras

demo:
	bash tests/demo/demo-up.sh

demo-scenarios:
	bash tests/demo/scenario_a_cert_renewal.sh
	bash tests/demo/scenario_b_evicted_pods.sh
	bash tests/demo/scenario_c_draft_postmortem.sh

demo-down:
	bash tests/demo/demo-down.sh

dashboard:
	uv run mcp-k8s-utility dashboard --port 8080

test:
	uv run pytest -v

gate:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages/server/src
	uv run pytest -v

clean:
	rm -rf .venv dist dist-* .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
