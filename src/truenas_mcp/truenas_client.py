"""TrueNAS API client wrapping the official truenas_api_client."""

import asyncio
import functools
from typing import Any, Dict, List, Optional, Tuple

import structlog
from truenas_api_client import Client as TNClient, ClientException

logger = structlog.get_logger(__name__)

# Request timeout in seconds
REQUEST_TIMEOUT = 30


class TrueNASConnectionError(Exception):
    """TrueNAS connection error."""


class TrueNASAuthenticationError(Exception):
    """TrueNAS authentication error."""


class TrueNASAPIError(Exception):
    """TrueNAS API error."""


class TrueNASClient:
    """Async wrapper around the official TrueNAS API client.

    Uses truenas_api_client (synchronous, websocket-client based) with
    asyncio.run_in_executor() for non-blocking operation in the MCP server.

    Supports two auth modes:
    - Password auth (PASSWORD_PLAIN): Preferred, no transport restrictions.
    - API key auth (API_KEY_PLAIN): Subject to TrueNAS NEP secure_transport
      check which auto-revokes keys on connections it considers insecure.
    """

    def __init__(
        self,
        host: str,
        username: str = "mcp-service",
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        port: int = 443,
        protocol: str = "wss",
        ssl_verify: bool = True,
    ) -> None:
        """Initialize TrueNAS client.

        Args:
            host: TrueNAS hostname or IP.
            username: Username for authentication.
            password: Password for PASSWORD_PLAIN auth (preferred).
            api_key: API key for API_KEY_PLAIN auth (fallback).
            port: WebSocket port (default 443).
            protocol: ws or wss (default wss).
            ssl_verify: Whether to verify SSL certificates.
        """
        if not password and not api_key:
            raise ValueError("Either password or api_key must be provided")

        self.host = host
        self.username = username
        self.password = password
        self.api_key = api_key
        self.port = port
        self.protocol = protocol
        self.ssl_verify = ssl_verify

        self._client: Optional[TNClient] = None
        self.authenticated = False

    @property
    def url(self) -> str:
        """Get WebSocket URL."""
        return f"{self.protocol}://{self.host}:{self.port}/api/current"

    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous function in a thread executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, functools.partial(func, *args, **kwargs)
        )

    def _connect_sync(self) -> None:
        """Synchronous connect and authenticate.

        Uses PASSWORD_PLAIN (via auth.login) if a password is configured,
        falling back to API_KEY_PLAIN (via auth.login_ex) if only an API
        key is available. Password auth is preferred because TrueNAS NEP
        auto-revokes API keys used over connections it considers insecure.
        """
        self._client = TNClient(uri=self.url, verify_ssl=self.ssl_verify)

        if self.password:
            result = self._client.call(
                "auth.login", self.username, self.password, None
            )
            if not result:
                raise ValueError("Invalid username or password")
        elif self.api_key:
            resp = self._client.call("auth.login_ex", {
                "mechanism": "API_KEY_PLAIN",
                "username": self.username,
                "api_key": self.api_key,
            })
            resp_type = resp.get("response_type")
            if resp_type == "SUCCESS":
                return
            elif resp_type == "AUTH_ERR":
                raise ValueError("Invalid API key or username")
            elif resp_type == "EXPIRED":
                raise ValueError("API key has been revoked or expired")
            else:
                raise ValueError(f"Unexpected auth response: {resp_type}")

    async def connect(self) -> None:
        """Connect to TrueNAS WebSocket API and authenticate."""
        try:
            logger.info("Connecting to TrueNAS", url=self.url, username=self.username)
            await self._run_sync(self._connect_sync)
            self.authenticated = True
            logger.info("Connected and authenticated to TrueNAS successfully")
        except ClientException as e:
            logger.error("Failed to connect to TrueNAS", error=str(e))
            raise TrueNASConnectionError(f"Connection failed: {e}")
        except ValueError as e:
            logger.error("Authentication failed", error=str(e))
            raise TrueNASAuthenticationError(f"Authentication failed: {e}")
        except Exception as e:
            logger.error("Unexpected error connecting to TrueNAS", error=str(e))
            raise TrueNASConnectionError(f"Connection failed: {e}")

    async def disconnect(self) -> None:
        """Disconnect from TrueNAS."""
        if self._client:
            try:
                await self._run_sync(self._client.close)
            except Exception:
                pass
            self._client = None
            self.authenticated = False
            logger.info("Disconnected from TrueNAS")

    async def _call(self, method: str, *params: Any) -> Any:
        """Make an API call via the official client."""
        if not self._client:
            raise TrueNASConnectionError("Not connected to TrueNAS")

        try:
            result = await self._run_sync(self._client.call, method, *params)
            logger.debug("API call completed", method=method)
            return result
        except ClientException as e:
            error_str = str(e)
            if "ENOTAUTHENTICATED" in error_str:
                raise TrueNASAuthenticationError(f"Not authenticated: {e}")
            logger.error("API call failed", method=method, error=error_str)
            raise TrueNASAPIError(f"API call {method} failed: {e}")

    async def test_connection(self) -> bool:
        """Test connection to TrueNAS."""
        try:
            if not self.authenticated:
                await self.connect()

            result = await self._call("core.ping")
            return result == "pong"
        except Exception as e:
            logger.error("Connection test failed", error=str(e))
            return False

    async def list_custom_apps(self, status_filter: str = "all") -> List[Dict[str, Any]]:
        """List Custom Apps."""
        apps = await self._call("app.query")

        if status_filter != "all":
            apps = [app for app in apps if app.get("state", "").lower() == status_filter.lower()]

        return apps

    async def get_app_status(self, app_name: str) -> str:
        """Get Custom App status."""
        app_data = await self._call("app.get_instance", app_name)
        return app_data.get("state", "unknown")

    async def start_app(self, app_name: str) -> bool:
        """Start Custom App."""
        try:
            await self._call("app.start", app_name)
            return True
        except TrueNASAPIError:
            return False

    async def stop_app(self, app_name: str) -> bool:
        """Stop Custom App."""
        try:
            await self._call("app.stop", app_name)
            return True
        except TrueNASAPIError:
            return False

    async def deploy_app(
        self,
        app_name: str,
        compose_yaml: str,
        auto_start: bool = True,
    ) -> bool:
        """Deploy Custom App from Docker Compose."""
        from .compose_converter import DockerComposeConverter

        converter = DockerComposeConverter()
        app_config = await converter.convert(compose_yaml, app_name)

        try:
            await self._call("app.create", app_config)
        except TrueNASAPIError as e:
            logger.error("App deployment failed", error=str(e))
            return False

        if auto_start:
            await self.start_app(app_name)

        return True

    async def update_app(
        self,
        app_name: str,
        compose_yaml: str,
        force_recreate: bool = False,
    ) -> bool:
        """Update Custom App."""
        from .compose_converter import DockerComposeConverter

        converter = DockerComposeConverter()
        app_config = await converter.convert(compose_yaml, app_name)

        try:
            await self._call("app.update", app_name, app_config)
            return True
        except TrueNASAPIError:
            return False

    async def delete_app(self, app_name: str, delete_volumes: bool = False) -> bool:
        """Delete Custom App."""
        try:
            await self._call("app.delete", app_name, delete_volumes)
            return True
        except TrueNASAPIError:
            return False

    async def validate_compose(
        self,
        compose_yaml: str,
        check_security: bool = True,
    ) -> Tuple[bool, List[str]]:
        """Validate Docker Compose YAML."""
        from .validators import ComposeValidator

        validator = ComposeValidator()
        return await validator.validate(compose_yaml, check_security)

    async def get_app_logs(
        self,
        app_name: str,
        lines: int = 100,
        service_name: Optional[str] = None,
    ) -> str:
        """Get Custom App logs."""
        try:
            container_ids = await self._call("app.container_ids", app_name)
        except TrueNASAPIError as e:
            raise TrueNASAPIError(f"Failed to get container IDs: {e}")

        if not container_ids:
            return "No containers found for this app"

        container_id = container_ids[0]
        return (
            f"Logs for {app_name} (container {container_id}):\n"
            "[Log retrieval not fully implemented in TrueNAS API]"
        )
