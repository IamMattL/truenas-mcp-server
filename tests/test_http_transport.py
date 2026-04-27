"""Tests for the optional HTTP transport (Streamable HTTP via Starlette)."""

import os
from unittest.mock import patch

import pytest


@pytest.fixture
def mock_env():
    """Minimal env for the server to construct without a live TrueNAS."""
    env_vars = {
        "TRUENAS_HOST": "test.example.com",
        "TRUENAS_PASSWORD": "test-password",
        "MOCK_TRUENAS": "true",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


def test_create_http_app_returns_starlette(mock_env):
    """create_http_app builds a Starlette ASGI app with the expected routes."""
    from starlette.applications import Starlette

    from truenas_mcp.mcp_server import create_http_app

    app = create_http_app()
    assert isinstance(app, Starlette)

    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/ready" in paths
    assert "/mcp" in paths


def test_health_endpoint_returns_200(mock_env):
    """/health is unconditionally healthy — used by the Mesh connector."""
    from starlette.testclient import TestClient

    from truenas_mcp.mcp_server import create_http_app

    with TestClient(create_http_app()) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert body["transport"] == "http"


def test_ready_endpoint_returns_503_before_first_tool_call(mock_env):
    """/ready is 503 until a tool call has lazily connected to TrueNAS."""
    from starlette.testclient import TestClient

    from truenas_mcp.mcp_server import create_http_app

    with TestClient(create_http_app()) as client:
        r = client.get("/ready")
        assert r.status_code == 503
        assert r.json()["status"] == "not_ready"


def test_main_rejects_unknown_transport():
    """An unrecognised MCP_TRANSPORT exits non-zero rather than starting stdio."""
    import asyncio

    from truenas_mcp.mcp_server import main

    with patch.dict(os.environ, {"MCP_TRANSPORT": "websocket"}, clear=False):
        with pytest.raises(SystemExit) as excinfo:
            asyncio.run(main())
        assert excinfo.value.code == 1
