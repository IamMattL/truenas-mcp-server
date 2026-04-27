"""Main MCP Server implementation for TrueNAS Scale Custom Apps.

Supports two transport modes selected by the ``MCP_TRANSPORT`` env var:

* ``stdio`` (default) — local clients (Claude Desktop, Claude Code) speak the
  MCP protocol over the process's stdin/stdout pipes.
* ``http`` — remote clients reach the server over HTTP. Authentication and
  authorisation are expected to be terminated upstream (Cloudflare Access /
  MCP Server Portal); this module just exposes the protocol on a plain HTTP
  endpoint so a portal can proxy to it.
"""

import asyncio
import os
import sys
from typing import Any, Dict, List

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from .discovery import DiscoveryToolsHandler
from .mcp_tools import MCPToolsHandler
from .truenas_client import TrueNASClient

logger = structlog.get_logger(__name__)


class TrueNASMCPServer:
    """MCP Server for TrueNAS Scale Custom Apps management."""

    def __init__(self) -> None:
        """Initialize the MCP server."""
        self.server = Server("truenas-scale-mcp")
        self.truenas_client: TrueNASClient | None = None
        self.tools_handler: MCPToolsHandler | None = None
        self.discovery_handler: DiscoveryToolsHandler | None = None
        self._init_lock = asyncio.Lock()
        
        # Configuration from environment
        self.config = {
            "truenas_host": os.getenv("TRUENAS_HOST", "nas.pvnkn3t.lan"),
            "truenas_password": os.getenv("TRUENAS_PASSWORD"),
            "truenas_api_key": os.getenv("TRUENAS_API_KEY"),
            "truenas_username": os.getenv("TRUENAS_USERNAME", "mcp-service"),
            "truenas_port": int(os.getenv("TRUENAS_PORT", "443")),
            "truenas_protocol": os.getenv("TRUENAS_PROTOCOL", "wss"),
            "ssl_verify": os.getenv("TRUENAS_SSL_VERIFY", "true").lower() == "true",
            "debug_mode": os.getenv("DEBUG_MODE", "false").lower() == "true",
            "mock_mode": os.getenv("MOCK_TRUENAS", "false").lower() == "true",
            "discovery_mode": os.getenv("MCP_DISCOVERY_MODE", "false").lower() == "true",
        }
        
        # Setup logging
        self._setup_logging()
        
        # Register MCP handlers
        self._register_handlers()

    def _setup_logging(self) -> None:
        """Configure structured logging."""
        log_level = "DEBUG" if self.config["debug_mode"] else "INFO"
        
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        logger.info(
            "TrueNAS MCP Server initializing",
            host=self.config["truenas_host"],
            mock_mode=self.config["mock_mode"],
            debug_mode=self.config["debug_mode"],
        )

    def _register_handlers(self) -> None:
        """Register MCP protocol handlers."""
        # Static tool definitions - no connection needed
        static_tools_handler = MCPToolsHandler(None)

        if self.config["discovery_mode"]:
            self.discovery_handler = DiscoveryToolsHandler(
                catalog_handler=static_tools_handler,
                exec_handler_provider=self._get_live_tools_handler,
            )
            logger.info(
                "Dynamic tool discovery enabled",
                tools_exposed=2,
                note="search_tools + execute_tool replace the full registry",
            )

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available MCP tools (static, no connection required)."""
            if self.discovery_handler is not None:
                return await self.discovery_handler.list_tools()
            return await static_tools_handler.list_tools()

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> Any:
            """Execute an MCP tool (connects on first call)."""
            if self.discovery_handler is not None:
                result = await self.discovery_handler.call_tool(name, arguments)
                return [result]
            if not self.tools_handler:
                await self._initialize_clients()
            result = await self.tools_handler.call_tool(name, arguments)
            return [result]

    async def _get_live_tools_handler(self) -> MCPToolsHandler:
        """Return the client-backed tools handler, initializing it on demand."""
        if not self.tools_handler:
            await self._initialize_clients()
        assert self.tools_handler is not None
        return self.tools_handler

    async def _initialize_clients(self) -> None:
        """Initialize TrueNAS client and tools handler (thread-safe)."""
        async with self._init_lock:
            if self.tools_handler is not None:
                return  # Already initialized
            await self._do_initialize_clients()

    async def _do_initialize_clients(self) -> None:
        """Perform actual client initialization."""
        if self.config["mock_mode"]:
            from .mock_client import MockTrueNASClient
            self.truenas_client = MockTrueNASClient()
            logger.info("Using mock TrueNAS client for development")
        else:
            if not self.config["truenas_password"] and not self.config["truenas_api_key"]:
                raise ValueError("TRUENAS_PASSWORD or TRUENAS_API_KEY environment variable required")

            self.truenas_client = TrueNASClient(
                host=self.config["truenas_host"],
                username=self.config["truenas_username"],
                password=self.config["truenas_password"],
                api_key=self.config["truenas_api_key"],
                port=self.config["truenas_port"],
                protocol=self.config["truenas_protocol"],
                ssl_verify=self.config["ssl_verify"],
            )
            
            # Test connection
            await self.truenas_client.connect()
            logger.info("Connected to TrueNAS", host=self.config["truenas_host"])
        
        # Initialize tools handler
        self.tools_handler = MCPToolsHandler(self.truenas_client)

    async def run(self, read_stream, write_stream) -> None:
        """Run the MCP server."""
        logger.info("Starting TrueNAS MCP Server")
        init_options = self.server.create_initialization_options()
        await self.server.run(read_stream, write_stream, init_options)

    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self.truenas_client:
            await self.truenas_client.disconnect()
        logger.info("TrueNAS MCP Server shutdown complete")


def create_http_app() -> Any:
    """Build a Starlette ASGI app that speaks MCP over Streamable HTTP.

    The app exposes three routes:

    * ``GET /health`` — liveness probe (always 200; used by load balancers
      and the Cloudflare Mesh connector to confirm the process is up).
    * ``GET /ready`` — readiness probe (200 once the TrueNAS client is
      initialised, 503 before the first tool call has run lazily).
    * ``GET|POST|DELETE /mcp`` — the MCP Streamable HTTP endpoint. Each
      session opened by a client gets its own ``StreamableHTTPServerTransport``
      keyed by the ``Mcp-Session-Id`` request header.

    No auth middleware is wired in here: this app is intended to sit behind
    a Cloudflare Server Portal (or another zero-trust front end) that
    terminates identity, device posture, and per-tool policy. Exposing the
    raw HTTP endpoint to the public internet is not supported.
    """
    # Imports are scoped to this function so stdio-only deployments don't
    # need starlette/uvicorn installed.
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from mcp.server.streamable_http import StreamableHTTPServerTransport
    from mcp.server.transport_security import TransportSecuritySettings

    allowed_origins_env = os.getenv("MCP_ALLOWED_ORIGINS", "")
    allowed_origins = (
        [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
        if allowed_origins_env
        else ["*"]
    )

    mcp_server_instance = TrueNASMCPServer()

    security_settings = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_origins=allowed_origins,
    )

    sessions: Dict[str, StreamableHTTPServerTransport] = {}

    async def handle_mcp(request: Any) -> Any:
        session_id = request.headers.get("Mcp-Session-Id")

        if session_id and session_id in sessions:
            transport = sessions[session_id]
            return await transport.handle_request(
                request.scope, request.receive, request._send
            )

        import uuid

        new_session_id = str(uuid.uuid4())
        transport = StreamableHTTPServerTransport(
            mcp_session_id=new_session_id,
            is_json_response_enabled=True,
            security_settings=security_settings,
        )
        sessions[new_session_id] = transport

        async def run_mcp_session() -> None:
            try:
                async with transport.connect() as (read_stream, write_stream):
                    await mcp_server_instance.run(read_stream, write_stream)
            except Exception as e:
                logger.error(
                    "MCP session error", session_id=new_session_id, error=str(e)
                )
            finally:
                sessions.pop(new_session_id, None)
                logger.info("MCP session ended", session_id=new_session_id)

        asyncio.create_task(run_mcp_session())

        return await transport.handle_request(
            request.scope, request.receive, request._send
        )

    async def health_check(_: Any) -> JSONResponse:
        return JSONResponse(
            {
                "status": "healthy",
                "service": "truenas-mcp-server",
                "transport": "http",
            }
        )

    async def ready_check(_: Any) -> JSONResponse:
        is_ready = mcp_server_instance.tools_handler is not None
        return JSONResponse(
            {"status": "ready" if is_ready else "not_ready"},
            status_code=200 if is_ready else 503,
        )

    return Starlette(
        routes=[
            Route("/health", health_check, methods=["GET"]),
            Route("/ready", ready_check, methods=["GET"]),
            Route("/mcp", handle_mcp, methods=["GET", "POST", "DELETE"]),
        ],
    )


async def _run_stdio() -> None:
    server = TrueNASMCPServer()
    try:
        async with stdio_server() as streams:
            await server.run(*streams)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error("Server error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        await server.cleanup()


async def _run_http() -> None:
    import uvicorn

    host = os.getenv("MCP_HTTP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_HTTP_PORT", "8080"))

    logger.info("Starting HTTP transport", host=host, port=port)
    config = uvicorn.Config(create_http_app(), host=host, port=port, log_level="info")
    await uvicorn.Server(config).serve()


async def main() -> None:
    """Run the server in the transport selected by ``MCP_TRANSPORT``."""
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        await _run_http()
    elif transport == "stdio":
        await _run_stdio()
    else:
        logger.error("Unknown MCP_TRANSPORT", value=transport)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())