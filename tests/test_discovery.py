"""Tests for dynamic tool discovery."""

import json
import os
from unittest.mock import patch

import pytest

from truenas_mcp.discovery import (
    EXECUTE_TOOL,
    SEARCH_TOOL,
    DiscoveryToolsHandler,
    _TOOL_CATEGORIES,
)
from truenas_mcp.mcp_server import TrueNASMCPServer
from truenas_mcp.mcp_tools import MCPToolsHandler
from truenas_mcp.mock_client import MockTrueNASClient


@pytest.fixture
async def live_handler():
    """MCPToolsHandler with a connected mock client."""
    client = MockTrueNASClient()
    await client.connect()
    return MCPToolsHandler(client)


@pytest.fixture
async def discovery_handler(live_handler):
    """DiscoveryToolsHandler wrapping a static catalog + a live handler."""
    catalog = MCPToolsHandler(None)

    async def provider():
        return live_handler

    return DiscoveryToolsHandler(catalog_handler=catalog, exec_handler_provider=provider)


class TestDiscoveryHandler:
    """Validate the search + execute meta-tool surface."""

    @pytest.mark.asyncio
    async def test_list_tools_only_returns_two_meta_tools(self, discovery_handler):
        tools = await discovery_handler.list_tools()
        assert len(tools) == 2
        names = [t.name for t in tools]
        assert names == ["search_tools", "execute_tool"]

    @pytest.mark.asyncio
    async def test_search_empty_returns_all_tools_grouped(self, discovery_handler):
        result = await discovery_handler.call_tool("search_tools", {})
        payload = json.loads(result.text)

        assert payload["total_matches"] == 33
        assert payload["returned"] <= 25
        assert payload["truncated"] is True
        # Every returned summary must have name/category/description.
        for entry in payload["tools"]:
            assert "name" in entry and "category" in entry and "description" in entry

    @pytest.mark.asyncio
    async def test_search_by_query(self, discovery_handler):
        result = await discovery_handler.call_tool(
            "search_tools", {"query": "snapshot"}
        )
        payload = json.loads(result.text)
        names = {t["name"] for t in payload["tools"]}
        assert {"create_snapshot", "delete_snapshot", "list_snapshots"} <= names
        # Sanity: unrelated tools are filtered out.
        assert "get_system_info" not in names

    @pytest.mark.asyncio
    async def test_search_by_category(self, discovery_handler):
        result = await discovery_handler.call_tool(
            "search_tools", {"category": "vm"}
        )
        payload = json.loads(result.text)
        assert payload["total_matches"] == sum(
            1 for c in _TOOL_CATEGORIES.values() if c == "vm"
        )
        assert all(t["category"] == "vm" for t in payload["tools"])

    @pytest.mark.asyncio
    async def test_search_returns_full_schema_for_exact_name(self, discovery_handler):
        result = await discovery_handler.call_tool(
            "search_tools", {"name": "create_snapshot"}
        )
        payload = json.loads(result.text)
        assert payload["name"] == "create_snapshot"
        assert payload["category"] == "storage"
        schema = payload["inputSchema"]
        assert schema["type"] == "object"
        assert "dataset" in schema["properties"]
        assert "name" in schema["properties"]

    @pytest.mark.asyncio
    async def test_search_unknown_name(self, discovery_handler):
        result = await discovery_handler.call_tool(
            "search_tools", {"name": "nope_not_a_tool"}
        )
        payload = json.loads(result.text)
        assert "error" in payload

    @pytest.mark.asyncio
    async def test_execute_routes_to_live_handler(self, discovery_handler):
        result = await discovery_handler.call_tool(
            "execute_tool",
            {"name": "test_connection", "arguments": {}},
        )
        assert result.type == "text"
        assert "connection successful" in result.text.lower()

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_rejected(self, discovery_handler):
        result = await discovery_handler.call_tool(
            "execute_tool",
            {"name": "bogus_tool", "arguments": {}},
        )
        assert "not found" in result.text.lower()

    @pytest.mark.asyncio
    async def test_execute_requires_name(self, discovery_handler):
        result = await discovery_handler.call_tool(
            "execute_tool", {"arguments": {}}
        )
        assert "requires a 'name'" in result.text

    @pytest.mark.asyncio
    async def test_execute_rejects_non_object_arguments(self, discovery_handler):
        result = await discovery_handler.call_tool(
            "execute_tool",
            {"name": "test_connection", "arguments": "not-an-object"},
        )
        assert "must be an object" in result.text

    @pytest.mark.asyncio
    async def test_unknown_meta_tool(self, discovery_handler):
        result = await discovery_handler.call_tool("whatever", {})
        assert "Unknown discovery tool" in result.text

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, discovery_handler):
        result = await discovery_handler.call_tool(
            "search_tools", {"limit": 3}
        )
        payload = json.loads(result.text)
        assert payload["returned"] == 3
        assert len(payload["tools"]) == 3

    def test_static_tool_definitions(self):
        """Meta-tool schemas should advertise required params explicitly."""
        assert SEARCH_TOOL.inputSchema["additionalProperties"] is False
        assert "name" in EXECUTE_TOOL.inputSchema["required"]


class TestDiscoveryServerIntegration:
    """Ensure the server wires discovery mode in correctly."""

    @pytest.fixture
    def discovery_env(self):
        env = {
            "TRUENAS_HOST": "test.example.com",
            "TRUENAS_PASSWORD": "test-password",
            "MCP_DISCOVERY_MODE": "true",
            "MOCK_TRUENAS": "true",
        }
        with patch.dict(os.environ, env, clear=False):
            yield env

    @pytest.mark.asyncio
    async def test_server_exposes_two_tools_in_discovery_mode(self, discovery_env):
        server = TrueNASMCPServer()
        assert server.config["discovery_mode"] is True
        assert server.discovery_handler is not None

        tools = await server.discovery_handler.list_tools()
        assert [t.name for t in tools] == ["search_tools", "execute_tool"]

    @pytest.mark.asyncio
    async def test_server_defaults_to_full_registry(self):
        with patch.dict(os.environ, {"MOCK_TRUENAS": "true"}, clear=False):
            server = TrueNASMCPServer()
            assert server.config["discovery_mode"] is False
            assert server.discovery_handler is None

    @pytest.mark.asyncio
    async def test_discovery_execute_initializes_client_lazily(self, discovery_env):
        server = TrueNASMCPServer()
        assert server.tools_handler is None

        result = await server.discovery_handler.call_tool(
            "execute_tool",
            {"name": "test_connection", "arguments": {}},
        )
        assert "connection successful" in result.text.lower()
        # Live handler was materialized on demand.
        assert server.tools_handler is not None
