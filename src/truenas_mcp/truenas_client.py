"""TrueNAS API client wrapping the official truenas_api_client."""

import asyncio
import functools
import os
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
        """Make an API call via the official client.

        Automatically reconnects once if the WebSocket has been dropped.
        """
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

            # Detect dead WebSocket and reconnect once
            if any(s in error_str.lower() for s in ("closure", "closed", "broken pipe", "connection")):
                logger.warning("Connection lost, reconnecting", method=method)
                try:
                    await self.disconnect()
                    await self.connect()
                    result = await self._run_sync(self._client.call, method, *params)
                    logger.info("Reconnect succeeded", method=method)
                    return result
                except Exception as retry_err:
                    logger.error("Reconnect failed", method=method, error=str(retry_err))
                    raise TrueNASAPIError(f"API call {method} failed after reconnect: {retry_err}")

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

    async def get_app_config(self, app_name: str) -> Dict[str, Any]:
        """Get full Custom App configuration."""
        return await self._call("app.get_instance", app_name)

    async def update_app_config(self, app_name: str, config: Dict[str, Any]) -> bool:
        """Update Custom App configuration with a raw config dict."""
        try:
            # Verify app exists first (app.update silently accepts nonexistent apps)
            await self._call("app.get_instance", app_name)
            await self._call("app.update", app_name, config)
            return True
        except TrueNASAPIError:
            return False

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
        """Get Custom App logs via event source subscription.

        Subscribes to ``app.container_log_follow`` to collect historical log
        lines, then unsubscribes.  Only works for RUNNING / CRASHED / DEPLOYING
        apps (TrueNAS refuses to stream logs from stopped containers).
        """
        # Step 1 – get app state and container details
        app_data = await self._call("app.get_instance", app_name)
        state = app_data.get("state", "UNKNOWN")

        if state not in ("RUNNING", "CRASHED", "DEPLOYING"):
            return (
                f"Cannot retrieve logs: app '{app_name}' is {state}. "
                "Start the app first."
            )

        workloads = app_data.get("active_workloads") or {}
        container_details = workloads.get("container_details") or []

        if not container_details:
            return f"No containers found for app '{app_name}'"

        # Optionally filter by service name
        if service_name:
            containers = [
                c for c in container_details
                if c.get("service_name") == service_name
            ]
            if not containers:
                available = ", ".join(
                    c.get("service_name", "?") for c in container_details
                )
                return (
                    f"Service '{service_name}' not found. "
                    f"Available: {available}"
                )
        else:
            containers = container_details

        # Step 2 – collect logs from each container
        all_logs: List[str] = []
        for ctr in containers:
            cid = ctr.get("id")
            svc = ctr.get("service_name", "?")
            if not cid:
                continue

            logs = await self._collect_container_logs(app_name, cid, lines)
            if logs:
                if len(containers) > 1:
                    all_logs.append(f"=== {svc} ===")
                all_logs.append(logs)

        return (
            "\n".join(all_logs)
            if all_logs
            else f"No log data for app '{app_name}'"
        )

    async def _collect_container_logs(
        self,
        app_name: str,
        container_id: str,
        tail_lines: int = 100,
        timeout: int = 5,
    ) -> str:
        """Collect container logs via event-source subscription.

        TrueNAS event sources encode args in the event name using a colon
        delimiter: ``event_name:json_args_string``.  The middleware's
        ``EventSourceManager.short_name_arg()`` splits on ``:`` to extract
        the JSON arg which is then validated by ``EventSource.validate_arg()``.

        This works with both JSONRPC and legacy WebSocket protocols.
        """
        import json as _json
        import threading

        collected: List[str] = []
        done = threading.Event()

        def _on_log(msg_type, **kwargs):
            fields = kwargs.get("fields") or {}
            data = fields.get("data", "")
            if data:
                ts = fields.get("timestamp", "")
                line = f"[{ts}] {data}" if ts else data
                collected.append(line.rstrip())
            if len(collected) >= tail_lines:
                done.set()

        # Encode event source args in the event name (colon-delimited JSON)
        args_json = _json.dumps({
            "app_name": app_name,
            "container_id": container_id,
            "tail_lines": tail_lines,
        })
        event_name = f"app.container_log_follow:{args_json}"

        def _subscribe_and_collect():
            sub_id = self._client.subscribe(event_name, _on_log)
            try:
                done.wait(timeout=timeout)
            finally:
                self._client.unsubscribe(sub_id)

        await self._run_sync(_subscribe_and_collect)
        return "\n".join(collected)

    # ── Docker Compose Config ────────────────────────────────────────

    async def get_compose_config(self, app_name: str) -> Dict[str, Any]:
        """Get the stored Docker Compose config for a Custom App.

        Calls ``app.config`` which returns the parsed ``user_config.yaml``
        — for custom apps this is the Docker Compose structure.
        """
        return await self._call("app.config", app_name)

    async def update_compose_config(
        self, app_name: str, compose_yaml: str
    ) -> bool:
        """Update the Docker Compose config for a Custom App.

        Passes the raw YAML string via ``custom_compose_config_string``
        which TrueNAS writes to both ``user_config.yaml`` and the
        rendered ``docker-compose.yaml``.
        """
        try:
            await self._call("app.get_instance", app_name)
            await self._call("app.update", app_name, {
                "custom_compose_config_string": compose_yaml,
            })
            return True
        except TrueNASAPIError:
            return False

    # ── Filesystem Tools ──────────────────────────────────────────────

    async def list_directory(
        self,
        path: str = "/mnt",
        include_hidden: bool = False,
    ) -> List[Dict[str, Any]]:
        """List directory contents, restricted to /mnt/."""
        normalized = os.path.normpath(path)
        if not normalized.startswith("/mnt"):
            raise ValueError("Path must be under /mnt/")

        entries = await self._call("filesystem.listdir", normalized)

        if not include_hidden:
            entries = [e for e in entries if not e.get("name", "").startswith(".")]

        return entries

    # ── ZFS Dataset / Snapshot Tools ──────────────────────────────────

    async def list_datasets(
        self,
        pool_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List ZFS datasets, optionally filtered by pool."""
        if pool_name:
            return await self._call(
                "pool.dataset.query",
                [["pool", "=", pool_name]],
            )
        return await self._call("pool.dataset.query")

    async def list_snapshots(
        self,
        dataset: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List ZFS snapshots, optionally filtered by dataset."""
        if dataset:
            return await self._call(
                "zfs.snapshot.query",
                [["dataset", "=", dataset]],
            )
        return await self._call("zfs.snapshot.query")

    async def create_snapshot(
        self,
        dataset: str,
        name: str,
        recursive: bool = False,
    ) -> Dict[str, Any]:
        """Create a ZFS snapshot."""
        if "/" not in dataset:
            raise ValueError(
                "Dataset must be in pool/dataset format (e.g. 'Store/Media')"
            )

        return await self._call("zfs.snapshot.create", {
            "dataset": dataset,
            "name": name,
            "recursive": recursive,
        })

    async def delete_snapshot(self, snapshot_name: str) -> bool:
        """Delete a ZFS snapshot by full name (e.g. 'Store/Media@snap1')."""
        try:
            await self._call("zfs.snapshot.delete", snapshot_name)
            return True
        except TrueNASAPIError:
            return False

    # ── System / Pool / Network Info ──────────────────────────────────

    async def get_system_info(self) -> Dict[str, Any]:
        """Get TrueNAS system information."""
        return await self._call("system.info")

    async def get_storage_pools(self) -> List[Dict[str, Any]]:
        """Get storage pool information."""
        return await self._call("pool.query")

    async def get_network_info(self) -> List[Dict[str, Any]]:
        """Get network interface information."""
        return await self._call("interface.query")
