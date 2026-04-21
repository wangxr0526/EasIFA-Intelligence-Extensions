from __future__ import annotations

import asyncio

from easifa_mcp.config import EasifaMCPSettings
from easifa_mcp.server import create_server


def test_server_registers_only_four_http_proxy_tools():
    settings = EasifaMCPSettings(
        agent_base_url="http://localhost:8011/easifa-agent",
        backend_base_url="http://localhost:8006/easifa",
    )
    mcp, client = create_server(settings)
    tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}

    try:
        assert tool_names == {
            "query-uniprot",
            "query-uniprot-sites",
            "batch-analyze",
            "batch-analyze-sequences",
            "analyze-structure",
            "get-job-result",
        }
    finally:
        asyncio.run(client.aclose())
