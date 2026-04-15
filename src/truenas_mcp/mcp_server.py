"""Main MCP Server implementation for TrueNAS Scale Custom Apps.

Supports two transport modes:
  - stdio (default): For local MCP clients (Claude Desktop, Claude Code, etc.)
  - http: Remote Streamable HTTP transport for deployment behind Cloudflare
          AI Controls (Access, AI Gateway, MCP Server Portals)

Transport mode is selected via the MCP_TRANSPORT environment variable.
"""

import asyncio
import os
import sys
from typing import Any, Dict, List

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

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

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available MCP tools (static, no connection required)."""
            return await static_tools_handler.list_tools()

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> Any:
            """Execute an MCP tool (connects on first call)."""
            if not self.tools_handler:
                await self._initialize_clients()
            result = await self.tools_handler.call_tool(name, arguments)
            return [result]

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
    """Create a Starlette ASGI app for remote HTTP transport.

    This wraps the MCP server with:
    - Streamable HTTP transport (MCP SDK)
    - Cloudflare Access JWT validation middleware
    - Rate limiting middleware (defense-in-depth)
    - Health check endpoints

    The app is designed to run behind:
    - Cloudflare Tunnel (for self-hosted TrueNAS)
    - Cloudflare Access (for authentication/identity)
    - Cloudflare AI Gateway (for rate limiting, logging, caching)
    - Cloudflare MCP Server Portal (for centralized governance)

    Returns:
        Starlette ASGI application
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    from mcp.server.streamable_http import StreamableHTTPServerTransport
    from mcp.server.transport_security import TransportSecuritySettings

    from .cloudflare_auth import CloudflareAccessMiddleware, RateLimitMiddleware

    # Cloudflare configuration from environment
    cf_team_domain = os.getenv("CF_ACCESS_TEAM_DOMAIN", "")
    cf_audience = os.getenv("CF_ACCESS_AUD", "")
    rate_limit_rpm = int(os.getenv("RATE_LIMIT_RPM", "60"))
    http_host = os.getenv("MCP_HTTP_HOST", "0.0.0.0")
    http_port = int(os.getenv("MCP_HTTP_PORT", "8080"))
    allowed_origins = os.getenv("MCP_ALLOWED_ORIGINS", "").split(",") if os.getenv("MCP_ALLOWED_ORIGINS") else []

    # Create the MCP server
    mcp_server_instance = TrueNASMCPServer()

    # Transport security settings
    security_settings = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_origins=allowed_origins or ["*"],
    )

    # Session management for Streamable HTTP
    sessions: Dict[str, StreamableHTTPServerTransport] = {}

    async def handle_mcp(request: Any) -> Any:
        """Handle MCP protocol requests via Streamable HTTP transport.

        Creates a new session on first request, reuses existing sessions
        for subsequent requests with the same session ID.
        """
        session_id = request.headers.get("Mcp-Session-Id")

        # For existing sessions, route to the existing transport
        if session_id and session_id in sessions:
            transport = sessions[session_id]
            return await transport.handle_request(
                request.scope, request.receive, request._send
            )

        # Create new transport for new sessions
        import uuid
        new_session_id = str(uuid.uuid4())
        transport = StreamableHTTPServerTransport(
            mcp_session_id=new_session_id,
            is_json_response_enabled=True,
            security_settings=security_settings,
        )

        sessions[new_session_id] = transport

        async def run_mcp_session() -> None:
            """Run the MCP server session in the background."""
            try:
                async with transport.connect() as (read_stream, write_stream):
                    await mcp_server_instance.run(read_stream, write_stream)
            except Exception as e:
                logger.error("MCP session error", session_id=new_session_id, error=str(e))
            finally:
                sessions.pop(new_session_id, None)
                logger.info("MCP session ended", session_id=new_session_id)

        # Start the session in the background
        asyncio.create_task(run_mcp_session())

        # Handle the initial request
        return await transport.handle_request(
            request.scope, request.receive, request._send
        )

    async def health_check(request: Any) -> JSONResponse:
        """Health check endpoint for Cloudflare Tunnel / load balancers."""
        return JSONResponse({
            "status": "healthy",
            "service": "truenas-mcp-server",
            "transport": "http",
            "cloudflare_access": "enabled" if cf_team_domain else "disabled",
        })

    async def ready_check(request: Any) -> JSONResponse:
        """Readiness check - verifies TrueNAS connectivity."""
        is_ready = mcp_server_instance.tools_handler is not None
        status_code = 200 if is_ready else 503
        return JSONResponse(
            {"status": "ready" if is_ready else "not_ready"},
            status_code=status_code,
        )

    # Build the Starlette app with routes
    app = Starlette(
        routes=[
            Route("/health", health_check, methods=["GET"]),
            Route("/ready", ready_check, methods=["GET"]),
            # MCP endpoint - handles POST (messages), GET (SSE stream), DELETE (session end)
            Route("/mcp", handle_mcp, methods=["GET", "POST", "DELETE"]),
        ],
    )

    # Add middleware (applied in reverse order - rate limit first, then auth)
    app.add_middleware(
        CloudflareAccessMiddleware,
        team_domain=cf_team_domain,
        audience=cf_audience,
    )
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=rate_limit_rpm,
    )

    logger.info(
        "HTTP transport configured",
        host=http_host,
        port=http_port,
        cloudflare_access="enabled" if cf_team_domain else "disabled",
        rate_limit_rpm=rate_limit_rpm,
    )

    return app


async def main() -> None:
    """Main entry point for the MCP server.

    Transport is selected via MCP_TRANSPORT environment variable:
      - "stdio" (default): Standard input/output for local MCP clients
      - "http": Streamable HTTP for remote access behind Cloudflare
    """
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()

    if transport == "http":
        import uvicorn

        app = create_http_app()
        host = os.getenv("MCP_HTTP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_HTTP_PORT", "8080"))

        logger.info("Starting HTTP transport", host=host, port=port)
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()
    else:
        # Default: stdio transport for local MCP clients
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


if __name__ == "__main__":
    asyncio.run(main())
