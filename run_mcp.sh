#!/usr/bin/env bash
# Stable entry point for the TrueNAS MCP server.
# Uses `poetry run` so it works regardless of virtualenv path.
cd "$(dirname "$0")"
exec poetry run python -m truenas_mcp.mcp_server
