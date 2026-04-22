from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from utility_server import __version__
from utility_server.dashboard.audit import load_recent_tool_calls
from utility_server.dashboard.health import probe_all
from utility_server.llm.adapter import UtilityLLM

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="mcp-k8s-utility dashboard", version=__version__)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": __version__})

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"version": __version__},
        )

    @app.get("/tiles/system-health", response_class=HTMLResponse)
    async def system_health(request: Request) -> HTMLResponse:
        statuses = await probe_all()
        return templates.TemplateResponse(
            request,
            "tiles/system_health.html",
            {"statuses": statuses},
        )

    @app.get("/tiles/llm-provider", response_class=HTMLResponse)
    async def llm_provider(request: Request) -> HTMLResponse:
        try:
            llm = UtilityLLM.from_env()
            provider = llm.provider_name
            error: str | None = None
        except ValueError as e:
            provider = "invalid"
            error = str(e)
        model = os.environ.get("UTILITY_LLM_MODEL", "(provider default)")
        return templates.TemplateResponse(
            request,
            "tiles/llm_provider.html",
            {"provider": provider, "model": model, "error": error},
        )

    @app.get("/tiles/tool-activity", response_class=HTMLResponse)
    async def tool_activity(request: Request) -> HTMLResponse:
        rows = await load_recent_tool_calls(limit=20)
        audit_path = os.environ.get("SECUREOPS_AUDIT_DB", "")
        return templates.TemplateResponse(
            request,
            "tiles/tool_activity.html",
            {"rows": rows, "audit_path": audit_path},
        )

    return app
