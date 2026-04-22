from __future__ import annotations

from fastmcp import FastMCP

mcp: FastMCP = FastMCP("mcp-k8s-utility")


def run_stdio() -> None:
    mcp.run(transport="stdio")
