from __future__ import annotations

from utility_server.mcp_server import mcp


async def test_renew_certificate_tools_registered():
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    required = {
        "list_expiring_certificates",
        "propose_certificate_renewal",
        "execute_certificate_renewal",
        "propose_right_size_plan",
        "list_evicted_pods",
        "propose_cleanup_plan",
        "execute_cleanup_plan",
        "list_noisy_alerts",
        "propose_alert_tuning",
    }
    missing = required - names
    assert not missing, f"missing tools: {missing}"
