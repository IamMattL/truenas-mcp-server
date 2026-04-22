"""Dynamic MCP tool discovery.

Inspired by Cloudflare's enterprise MCP deployment findings: registering every
tool upfront scales poorly because the full tool list is shipped in every
request's context window. For 33 tools the schemas easily exceed 9k tokens.

This module collapses the full registry into two meta-tools:

* ``search_tools`` — discover available tools on demand (by keyword, category,
  or exact name). Returns compact summaries, or the full schema for one tool.
* ``execute_tool`` — invoke any tool by name with a parameter object.

The underlying tool implementations live in :class:`MCPToolsHandler` and are
reused unchanged; this handler merely changes how they are surfaced to the
model.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog
from mcp.types import TextContent, Tool

from .mcp_tools import MCPToolsHandler

logger = structlog.get_logger(__name__)


# Static tool → category mapping. Kept in sync with the section comments in
# :mod:`truenas_mcp.mcp_tools`. Unknown tools fall back to "other".
_TOOL_CATEGORIES: Dict[str, str] = {
    "test_connection": "connection",
    "list_custom_apps": "app",
    "get_custom_app_status": "app",
    "get_custom_app_config": "app",
    "start_custom_app": "app",
    "stop_custom_app": "app",
    "deploy_custom_app": "app",
    "update_custom_app": "app",
    "update_custom_app_config": "app",
    "delete_custom_app": "app",
    "validate_compose": "app",
    "get_app_logs": "app",
    "get_compose_config": "app",
    "update_compose_config": "app",
    "list_directory": "filesystem",
    "read_file": "filesystem",
    "list_datasets": "storage",
    "list_snapshots": "storage",
    "create_snapshot": "storage",
    "delete_snapshot": "storage",
    "create_vm": "vm",
    "add_vm_device": "vm",
    "query_vm_devices": "vm",
    "update_vm_device": "vm",
    "list_vms": "vm",
    "get_vm_status": "vm",
    "start_vm": "vm",
    "stop_vm": "vm",
    "poweroff_vm": "vm",
    "delete_vm": "vm",
    "get_system_info": "system",
    "get_storage_pools": "system",
    "get_network_info": "system",
}


SEARCH_TOOL = Tool(
    name="search_tools",
    description=(
        "Discover TrueNAS tools on demand. Provide a keyword `query`, a "
        "`category` (connection, app, filesystem, storage, vm, system), or an "
        "exact tool `name` to retrieve its full JSON schema. With no arguments "
        "returns every tool grouped by category. Use this before `execute_tool`."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keyword matched against tool names and descriptions (case-insensitive).",
            },
            "category": {
                "type": "string",
                "enum": [
                    "connection",
                    "app",
                    "filesystem",
                    "storage",
                    "vm",
                    "system",
                ],
                "description": "Restrict results to a single category.",
            },
            "name": {
                "type": "string",
                "description": "Exact tool name; returns the full input schema for that tool.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 25,
                "description": "Maximum number of summaries to return for keyword/category searches.",
            },
        },
        "additionalProperties": False,
    },
)


EXECUTE_TOOL = Tool(
    name="execute_tool",
    description=(
        "Execute any TrueNAS tool discovered via `search_tools`. Pass the tool "
        "`name` and an `arguments` object that matches the tool's input schema. "
        "Returns the same response the tool would return if called directly."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the tool to execute.",
            },
            "arguments": {
                "type": "object",
                "description": "Arguments conforming to the target tool's input schema.",
                "additionalProperties": True,
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
)


ExecHandlerProvider = Callable[[], Awaitable[MCPToolsHandler]]


class DiscoveryToolsHandler:
    """Expose the full tool registry as two meta-tools (search + execute)."""

    def __init__(
        self,
        catalog_handler: MCPToolsHandler,
        exec_handler_provider: ExecHandlerProvider,
    ) -> None:
        """Create a discovery handler.

        :param catalog_handler: Handler used only to enumerate tool metadata
            (no TrueNAS client required).
        :param exec_handler_provider: Async callable returning an initialized
            :class:`MCPToolsHandler` (with a connected TrueNAS client) for
            actually running tools.
        """
        self._catalog = catalog_handler
        self._get_exec_handler = exec_handler_provider
        self._cached_tools: Optional[List[Tool]] = None

    async def list_tools(self) -> List[Tool]:
        """Return only the two discovery meta-tools."""
        return [SEARCH_TOOL, EXECUTE_TOOL]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> TextContent:
        """Dispatch a discovery meta-tool call."""
        if name == "search_tools":
            return await self._search(arguments or {})
        if name == "execute_tool":
            return await self._execute(arguments or {})
        return TextContent(
            type="text",
            text=(
                f"❌ Unknown discovery tool '{name}'. "
                "Only 'search_tools' and 'execute_tool' are available."
            ),
        )

    async def _catalog_tools(self) -> List[Tool]:
        if self._cached_tools is None:
            self._cached_tools = await self._catalog.list_tools()
        return self._cached_tools

    async def _search(self, arguments: Dict[str, Any]) -> TextContent:
        tools = await self._catalog_tools()

        exact_name = arguments.get("name")
        if exact_name:
            match = next((t for t in tools if t.name == exact_name), None)
            if match is None:
                return TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": f"No tool named '{exact_name}'",
                            "hint": "Call search_tools with a query or category to list tools.",
                        },
                        indent=2,
                    ),
                )
            return TextContent(
                type="text",
                text=json.dumps(
                    {
                        "name": match.name,
                        "category": _TOOL_CATEGORIES.get(match.name, "other"),
                        "description": match.description,
                        "inputSchema": match.inputSchema,
                    },
                    indent=2,
                ),
            )

        query = (arguments.get("query") or "").strip().lower()
        category = arguments.get("category")
        limit = int(arguments.get("limit", 25))

        filtered: List[Tool] = []
        for tool in tools:
            tool_category = _TOOL_CATEGORIES.get(tool.name, "other")
            if category and tool_category != category:
                continue
            if query:
                haystack = f"{tool.name} {tool.description or ''}".lower()
                if query not in haystack:
                    continue
            filtered.append(tool)

        summaries = [
            {
                "name": tool.name,
                "category": _TOOL_CATEGORIES.get(tool.name, "other"),
                "description": tool.description,
            }
            for tool in filtered[:limit]
        ]

        payload: Dict[str, Any] = {
            "total_matches": len(filtered),
            "returned": len(summaries),
            "tools": summaries,
        }
        if len(filtered) > limit:
            payload["truncated"] = True
            payload["hint"] = (
                "Refine with `query`, `category`, or a larger `limit` to see more."
            )
        if not query and not category:
            payload["hint"] = (
                "Call search_tools again with `name=<tool>` to get the full input schema, "
                "then invoke execute_tool."
            )

        return TextContent(type="text", text=json.dumps(payload, indent=2))

    async def _execute(self, arguments: Dict[str, Any]) -> TextContent:
        target = arguments.get("name")
        if not target:
            return TextContent(
                type="text",
                text="❌ execute_tool requires a 'name' argument.",
            )
        args = arguments.get("arguments") or {}
        if not isinstance(args, dict):
            return TextContent(
                type="text",
                text="❌ execute_tool 'arguments' must be an object.",
            )

        logger.info("Discovery execute_tool", target=target, args=args)

        catalog = await self._catalog_tools()
        if not any(t.name == target for t in catalog):
            return TextContent(
                type="text",
                text=(
                    f"❌ Tool '{target}' not found. "
                    "Use search_tools to list available tools."
                ),
            )

        exec_handler = await self._get_exec_handler()
        return await exec_handler.call_tool(target, args)
