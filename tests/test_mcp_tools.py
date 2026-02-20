"""Tests for MCP tools implementation."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from truenas_mcp.mcp_tools import MCPToolsHandler
from truenas_mcp.mock_client import MockTrueNASClient


class TestMCPToolsHandler:
    """Test MCP tools functionality."""

    @pytest.fixture
    async def mock_client(self):
        """Create mock TrueNAS client."""
        return MockTrueNASClient()

    @pytest.fixture
    async def tools_handler(self, mock_client):
        """Create tools handler with mock client."""
        await mock_client.connect()
        return MCPToolsHandler(mock_client)

    @pytest.mark.asyncio
    async def test_list_tools(self, tools_handler):
        """Test tool listing returns all 22 tools."""
        tools = await tools_handler.list_tools()

        assert len(tools) == 22

        tool_names = [tool.name for tool in tools]
        expected_tools = [
            "test_connection",
            "list_custom_apps",
            "get_custom_app_status",
            "get_custom_app_config",
            "start_custom_app",
            "stop_custom_app",
            "deploy_custom_app",
            "update_custom_app",
            "update_custom_app_config",
            "delete_custom_app",
            "validate_compose",
            "get_app_logs",
            "get_compose_config",
            "update_compose_config",
            "list_directory",
            "list_datasets",
            "list_snapshots",
            "create_snapshot",
            "delete_snapshot",
            "get_system_info",
            "get_storage_pools",
            "get_network_info",
        ]

        for expected_tool in expected_tools:
            assert expected_tool in tool_names

    @pytest.mark.asyncio
    async def test_test_connection_success(self, tools_handler):
        """Test connection testing tool."""
        result = await tools_handler.call_tool("test_connection", {})
        
        assert result.type == "text"
        assert "✅" in result.text
        assert "connection successful" in result.text.lower()

    @pytest.mark.asyncio
    async def test_list_custom_apps_all(self, tools_handler):
        """Test listing all Custom Apps."""
        result = await tools_handler.call_tool("list_custom_apps", {"status_filter": "all"})
        
        assert result.type == "text"
        assert "Custom Apps:" in result.text
        assert "nginx-demo" in result.text
        assert "plex-server" in result.text
        assert "home-assistant" in result.text

    @pytest.mark.asyncio
    async def test_list_custom_apps_running_only(self, tools_handler):
        """Test listing only running Custom Apps."""
        result = await tools_handler.call_tool("list_custom_apps", {"status_filter": "running"})
        
        assert result.type == "text"
        assert "nginx-demo" in result.text
        assert "home-assistant" in result.text
        assert "plex-server" not in result.text  # This one is stopped

    @pytest.mark.asyncio
    async def test_get_custom_app_status(self, tools_handler):
        """Test getting Custom App status."""
        result = await tools_handler.call_tool("get_custom_app_status", {"app_name": "nginx-demo"})
        
        assert result.type == "text"
        assert "nginx-demo" in result.text
        assert "RUNNING" in result.text

    # ── Get/Update Config Tool Tests ────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_custom_app_config_running(self, tools_handler):
        """Test getting config of a running app."""
        result = await tools_handler.call_tool("get_custom_app_config", {"app_name": "nginx-demo"})

        assert result.type == "text"
        assert "nginx-demo" in result.text
        assert "nginx:latest" in result.text
        assert "8080:80" in result.text
        assert "NGINX_HOST" in result.text
        assert "/usr/share/nginx/html" in result.text

    @pytest.mark.asyncio
    async def test_get_custom_app_config_stopped(self, tools_handler):
        """Test getting config of a stopped app."""
        result = await tools_handler.call_tool("get_custom_app_config", {"app_name": "plex-server"})

        assert result.type == "text"
        assert "STOPPED" in result.text
        assert "plexinc/pms-docker" in result.text
        assert "PLEX_CLAIM" in result.text

    @pytest.mark.asyncio
    async def test_get_custom_app_config_nonexistent(self, tools_handler):
        """Test getting config of a nonexistent app."""
        result = await tools_handler.call_tool("get_custom_app_config", {"app_name": "nonexistent-app"})

        assert result.type == "text"
        assert "❌" in result.text

    @pytest.mark.asyncio
    async def test_update_custom_app_config_success(self, tools_handler):
        """Test updating app config successfully."""
        result = await tools_handler.call_tool("update_custom_app_config", {
            "app_name": "nginx-demo",
            "config": {"config": {"services": {"web": {"environment": {"NGINX_HOST": "example.com"}}}}},
        })

        assert result.type == "text"
        assert "✅" in result.text
        assert "nginx-demo" in result.text
        assert "config" in result.text

    @pytest.mark.asyncio
    async def test_update_custom_app_config_nonexistent(self, tools_handler):
        """Test updating config of a nonexistent app."""
        result = await tools_handler.call_tool("update_custom_app_config", {
            "app_name": "nonexistent-app",
            "config": {"config": {"services": {}}},
        })

        assert result.type == "text"
        assert "❌" in result.text

    @pytest.mark.asyncio
    async def test_update_custom_app_config_env_only(self, tools_handler):
        """Test updating just environment variables."""
        result = await tools_handler.call_tool("update_custom_app_config", {
            "app_name": "home-assistant",
            "config": {"config": {"services": {"hass": {"environment": {"TZ": "US/Eastern"}}}}},
        })

        assert result.type == "text"
        assert "✅" in result.text

    @pytest.mark.asyncio
    async def test_start_custom_app(self, tools_handler):
        """Test starting Custom App."""
        result = await tools_handler.call_tool("start_custom_app", {"app_name": "plex-server"})
        
        assert result.type == "text"
        assert "✅" in result.text
        assert "Started" in result.text
        assert "plex-server" in result.text

    @pytest.mark.asyncio
    async def test_stop_custom_app(self, tools_handler):
        """Test stopping Custom App."""
        result = await tools_handler.call_tool("stop_custom_app", {"app_name": "nginx-demo"})
        
        assert result.type == "text"
        assert "✅" in result.text
        assert "Stopped" in result.text
        assert "nginx-demo" in result.text

    @pytest.mark.asyncio
    async def test_deploy_custom_app(self, tools_handler):
        """Test deploying new Custom App."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx:latest
    ports:
      - "8080:80"
"""
        
        result = await tools_handler.call_tool("deploy_custom_app", {
            "app_name": "test-nginx",
            "compose_yaml": compose_yaml,
            "auto_start": True
        })
        
        assert result.type == "text"
        assert "✅" in result.text
        assert "Deployed" in result.text
        assert "test-nginx" in result.text

    @pytest.mark.asyncio
    async def test_update_custom_app(self, tools_handler):
        """Test updating existing Custom App."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx:1.25
    ports:
      - "8080:80"
"""
        
        result = await tools_handler.call_tool("update_custom_app", {
            "app_name": "nginx-demo",
            "compose_yaml": compose_yaml,
            "force_recreate": False
        })
        
        assert result.type == "text"
        assert "✅" in result.text
        assert "Updated" in result.text
        assert "nginx-demo" in result.text

    @pytest.mark.asyncio
    async def test_delete_custom_app_confirmed(self, tools_handler):
        """Test deleting Custom App with confirmation."""
        result = await tools_handler.call_tool("delete_custom_app", {
            "app_name": "nginx-demo",
            "delete_volumes": False,
            "confirm_deletion": True
        })

        assert result.type == "text"
        assert "✅" in result.text
        assert "Deleted" in result.text
        assert "nginx-demo" in result.text

    @pytest.mark.asyncio
    async def test_delete_custom_app_not_confirmed(self, tools_handler):
        """Test deleting Custom App without confirmation fails."""
        result = await tools_handler.call_tool("delete_custom_app", {
            "app_name": "test-app",
            "delete_volumes": False,
            "confirm_deletion": False
        })
        
        assert result.type == "text"
        assert "❌" in result.text
        assert "not confirmed" in result.text.lower()

    @pytest.mark.asyncio
    async def test_validate_compose_valid(self, tools_handler):
        """Test validating valid Docker Compose."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx:latest
    ports:
      - "8080:80"
"""
        
        result = await tools_handler.call_tool("validate_compose", {
            "compose_yaml": compose_yaml,
            "check_security": True
        })
        
        assert result.type == "text"
        assert "✅" in result.text
        assert "valid" in result.text.lower()

    @pytest.mark.asyncio
    async def test_get_app_logs(self, tools_handler):
        """Test getting Custom App logs for a running app."""
        result = await tools_handler.call_tool("get_app_logs", {
            "app_name": "nginx-demo",
            "lines": 50
        })

        assert result.type == "text"
        assert "Logs for" in result.text
        assert "nginx-demo" in result.text

    @pytest.mark.asyncio
    async def test_get_app_logs_stopped(self, tools_handler):
        """Test getting logs for a stopped app returns helpful message."""
        result = await tools_handler.call_tool("get_app_logs", {
            "app_name": "plex-server",
            "lines": 50
        })

        assert result.type == "text"
        assert "Cannot retrieve logs" in result.text
        assert "STOPPED" in result.text

    # ── Docker Compose Config Tool Tests ──────────────────────────────

    @pytest.mark.asyncio
    async def test_get_compose_config(self, tools_handler):
        """Test getting compose config returns YAML."""
        result = await tools_handler.call_tool("get_compose_config", {
            "app_name": "nginx-demo",
        })

        assert result.type == "text"
        assert "Docker Compose config" in result.text
        assert "nginx-demo" in result.text
        assert "nginx:latest" in result.text
        assert "yaml" in result.text  # code block marker

    @pytest.mark.asyncio
    async def test_get_compose_config_nonexistent(self, tools_handler):
        """Test getting compose config for nonexistent app."""
        result = await tools_handler.call_tool("get_compose_config", {
            "app_name": "nonexistent-app",
        })

        assert result.type == "text"
        assert "❌" in result.text

    @pytest.mark.asyncio
    async def test_update_compose_config(self, tools_handler):
        """Test updating compose config with new YAML."""
        new_yaml = """
services:
  web:
    image: nginx:1.27
    ports:
      - "8080:80"
"""
        result = await tools_handler.call_tool("update_compose_config", {
            "app_name": "nginx-demo",
            "compose_yaml": new_yaml,
        })

        assert result.type == "text"
        assert "✅" in result.text
        assert "nginx-demo" in result.text

    @pytest.mark.asyncio
    async def test_update_compose_config_nonexistent(self, tools_handler):
        """Test updating compose config for nonexistent app."""
        result = await tools_handler.call_tool("update_compose_config", {
            "app_name": "nonexistent-app",
            "compose_yaml": "services:\n  web:\n    image: nginx\n",
        })

        assert result.type == "text"
        assert "❌" in result.text

    @pytest.mark.asyncio
    async def test_invalid_tool_name(self, tools_handler):
        """Test calling invalid tool name returns error."""
        result = await tools_handler.call_tool("invalid_tool", {})
        
        assert result.type == "text"
        assert "❌" in result.text
        assert "Unknown tool" in result.text

    @pytest.mark.asyncio
    async def test_tool_execution_error_handling(self, tools_handler):
        """Test error handling in tool execution."""
        # Mock the client to raise an exception
        tools_handler.client.get_app_status = AsyncMock(side_effect=Exception("Mock error"))

        result = await tools_handler.call_tool("get_custom_app_status", {"app_name": "test"})

        assert result.type == "text"
        assert "❌" in result.text
        assert "Error executing" in result.text

    # ── Filesystem Tool Tests ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_directory_default(self, tools_handler):
        """Test listing /mnt directory."""
        result = await tools_handler.call_tool("list_directory", {})

        assert result.type == "text"
        assert "Directory: /mnt" in result.text
        assert "Store" in result.text
        assert "Boot" in result.text
        # Hidden files should be excluded by default
        assert ".zfs" not in result.text

    @pytest.mark.asyncio
    async def test_list_directory_with_hidden(self, tools_handler):
        """Test listing directory with hidden files included."""
        result = await tools_handler.call_tool("list_directory", {
            "path": "/mnt",
            "include_hidden": True,
        })

        assert result.type == "text"
        assert ".zfs" in result.text

    @pytest.mark.asyncio
    async def test_list_directory_subdirectory(self, tools_handler):
        """Test listing a subdirectory."""
        result = await tools_handler.call_tool("list_directory", {
            "path": "/mnt/Store/Media",
        })

        assert result.type == "text"
        assert "Movies" in result.text
        assert "TV Shows" in result.text
        assert "readme.txt" in result.text

    @pytest.mark.asyncio
    async def test_list_directory_path_restriction(self, tools_handler):
        """Test that paths outside /mnt/ are rejected."""
        result = await tools_handler.call_tool("list_directory", {
            "path": "/etc/passwd",
        })

        assert result.type == "text"
        assert "❌" in result.text

    @pytest.mark.asyncio
    async def test_list_directory_traversal_blocked(self, tools_handler):
        """Test that path traversal attempts are blocked."""
        result = await tools_handler.call_tool("list_directory", {
            "path": "/mnt/../../etc",
        })

        assert result.type == "text"
        assert "❌" in result.text

    # ── ZFS Dataset / Snapshot Tool Tests ─────────────────────────────

    @pytest.mark.asyncio
    async def test_list_datasets_all(self, tools_handler):
        """Test listing all datasets."""
        result = await tools_handler.call_tool("list_datasets", {})

        assert result.type == "text"
        assert "ZFS Datasets" in result.text
        assert "Store" in result.text
        assert "Store/Media" in result.text

    @pytest.mark.asyncio
    async def test_list_datasets_filtered(self, tools_handler):
        """Test listing datasets filtered by pool."""
        result = await tools_handler.call_tool("list_datasets", {
            "pool_name": "Boot",
        })

        assert result.type == "text"
        assert "Boot/ROOT" in result.text
        assert "Store/Media" not in result.text

    @pytest.mark.asyncio
    async def test_list_snapshots_all(self, tools_handler):
        """Test listing all snapshots."""
        result = await tools_handler.call_tool("list_snapshots", {})

        assert result.type == "text"
        assert "ZFS Snapshots" in result.text
        assert "pre-tdarr-20260215" in result.text
        assert "daily-20260217" in result.text

    @pytest.mark.asyncio
    async def test_list_snapshots_filtered(self, tools_handler):
        """Test listing snapshots filtered by dataset."""
        result = await tools_handler.call_tool("list_snapshots", {
            "dataset": "Store/Media",
        })

        assert result.type == "text"
        assert "pre-tdarr-20260215" in result.text
        assert "daily-20260217" not in result.text

    @pytest.mark.asyncio
    async def test_create_snapshot(self, tools_handler):
        """Test creating a snapshot."""
        result = await tools_handler.call_tool("create_snapshot", {
            "dataset": "Store/Media",
            "name": "test-snap",
        })

        assert result.type == "text"
        assert "✅" in result.text
        assert "Store/Media@test-snap" in result.text

    @pytest.mark.asyncio
    async def test_delete_snapshot_confirmed(self, tools_handler):
        """Test deleting a snapshot with confirmation."""
        result = await tools_handler.call_tool("delete_snapshot", {
            "snapshot_name": "Store/Media@pre-tdarr-20260215",
            "confirm_deletion": True,
        })

        assert result.type == "text"
        assert "✅" in result.text
        assert "Deleted" in result.text

    @pytest.mark.asyncio
    async def test_delete_snapshot_not_confirmed(self, tools_handler):
        """Test deleting a snapshot without confirmation."""
        result = await tools_handler.call_tool("delete_snapshot", {
            "snapshot_name": "Store/Media@pre-tdarr-20260215",
            "confirm_deletion": False,
        })

        assert result.type == "text"
        assert "❌" in result.text
        assert "not confirmed" in result.text.lower()

    # ── System / Pool / Network Tool Tests ────────────────────────────

    @pytest.mark.asyncio
    async def test_get_system_info(self, tools_handler):
        """Test getting system information."""
        result = await tools_handler.call_tool("get_system_info", {})

        assert result.type == "text"
        assert "TrueNAS System Info" in result.text
        assert "truenas" in result.text  # hostname
        assert "TrueNAS-SCALE" in result.text
        assert "i7-7700" in result.text

    @pytest.mark.asyncio
    async def test_get_storage_pools(self, tools_handler):
        """Test getting storage pool information."""
        result = await tools_handler.call_tool("get_storage_pools", {})

        assert result.type == "text"
        assert "Storage Pools" in result.text
        assert "Store" in result.text
        assert "ONLINE" in result.text
        assert "RAIDZ2" in result.text

    @pytest.mark.asyncio
    async def test_get_network_info(self, tools_handler):
        """Test getting network interface information."""
        result = await tools_handler.call_tool("get_network_info", {})

        assert result.type == "text"
        assert "Network Interfaces" in result.text
        assert "enp2s0" in result.text
        assert "192.168.10.249" in result.text
        assert "2500 Mbps" in result.text


class TestToolSchemas:
    """Test MCP tool schema validation."""

    @pytest.fixture
    async def tools_handler(self):
        """Create tools handler."""
        mock_client = MockTrueNASClient()
        await mock_client.connect()
        return MCPToolsHandler(mock_client)

    @pytest.mark.asyncio
    async def test_all_tools_have_valid_schemas(self, tools_handler):
        """Test all tools have valid JSON schemas."""
        tools = await tools_handler.list_tools()
        
        for tool in tools:
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
            assert hasattr(tool, 'inputSchema')
            
            schema = tool.inputSchema
            assert isinstance(schema, dict)
            assert schema.get("type") == "object"
            assert "properties" in schema
            assert "additionalProperties" in schema
            assert schema["additionalProperties"] is False

    @pytest.mark.asyncio
    async def test_app_name_pattern_validation(self, tools_handler):
        """Test app name pattern in tool schemas."""
        tools = await tools_handler.list_tools()
        
        app_name_tools = [
            "get_custom_app_status",
            "get_custom_app_config",
            "start_custom_app",
            "stop_custom_app",
            "deploy_custom_app",
            "update_custom_app",
            "update_custom_app_config",
            "delete_custom_app",
            "get_app_logs",
            "get_compose_config",
            "update_compose_config",
        ]
        
        for tool in tools:
            if tool.name in app_name_tools:
                app_name_prop = tool.inputSchema["properties"]["app_name"]
                assert app_name_prop["type"] == "string"
                assert "pattern" in app_name_prop
                assert app_name_prop["pattern"] == "^[a-z0-9][a-z0-9-]*[a-z0-9]$"