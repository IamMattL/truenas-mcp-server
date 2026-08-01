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

    async def _call(self, method: str, *params: Any, job: bool = False) -> Any:
        """Make an API call via the official client.

        Automatically reconnects once if the WebSocket has been dropped.

        Args:
            method: The API method to call.
            *params: Positional arguments for the API method.
            job: If True, wait for the TrueNAS job to complete and return
                 the job result instead of the job ID.
        """
        if not self._client:
            raise TrueNASConnectionError("Not connected to TrueNAS")

        def _do_call():
            return self._client.call(method, *params, job=job)

        try:
            result = await self._run_sync(_do_call)
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
                    result = await self._run_sync(_do_call)
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
        """Update Custom App configuration with a raw config dict.

        For the TrueNAS "Custom App" (ix-app) template, editable settings —
        ``envs``, ``ports``, ``image``, etc. — live under the ``values`` key,
        so the provided dict is wrapped accordingly. Passing it at the top
        level (as this used to) makes ``app.update`` silently ignore it.
        ``app.update`` runs as a job (a container rollout), so we wait for it
        to finish before returning success.
        """
        try:
            # Verify app exists first (app.update silently accepts nonexistent apps)
            await self._call("app.get_instance", app_name)
            await self._call("app.update", app_name, {"values": config}, job=True)
            return True
        except TrueNASAPIError:
            return False

    async def start_app(self, app_name: str) -> bool:
        """Start Custom App. app.start is a job, so wait for it to finish."""
        try:
            await self._call("app.start", app_name, job=True)
            return True
        except TrueNASAPIError:
            return False

    async def stop_app(self, app_name: str) -> bool:
        """Stop Custom App. app.stop is a job, so wait for it to finish."""
        try:
            await self._call("app.stop", app_name, job=True)
            return True
        except TrueNASAPIError:
            return False

    async def deploy_app(
        self,
        app_name: str,
        compose_yaml: str,
        auto_start: bool = True,
    ) -> str | None:
        """Deploy Custom App from Docker Compose.

        Returns None on success, or an error message string on failure.
        """
        app_config = {
            "app_name": app_name,
            "custom_app": True,
            "custom_compose_config_string": compose_yaml,
            "train": "stable",
            "version": "latest",
        }

        try:
            await self._call("app.create", app_config, job=True)
        except (TrueNASAPIError, Exception) as e:
            logger.error("App deployment failed", error=str(e))
            return str(e)

        return None

    async def update_app(
        self,
        app_name: str,
        compose_yaml: str,
        force_recreate: bool = False,
    ) -> bool:
        """Update Custom App."""
        update_config = {
            "custom_compose_config_string": compose_yaml,
        }

        try:
            await self._call("app.update", app_name, update_config, job=True)
            return True
        except TrueNASAPIError:
            return False

    async def delete_app(self, app_name: str, delete_volumes: bool = False) -> bool:
        """Delete Custom App.

        app.delete takes an options object (not a bare bool) and is a job, so
        the call must wait for completion. Without job=True it returns as soon
        as the job is queued, reporting success even when the delete fails.
        """
        options = {
            "remove_images": True,
            "remove_ix_volumes": delete_volumes,
            # ix_volumes holding data are skipped unless removal is forced.
            "force_remove_ix_volumes": delete_volumes,
        }
        try:
            await self._call("app.delete", app_name, options, job=True)
        except TrueNASAPIError:
            return False

        # Confirm the app is actually gone rather than trusting the job result.
        remaining = await self._call("app.query", [["name", "=", app_name]])
        return not remaining

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

    async def read_file(
        self,
        path: str,
        tail_lines: int = 0,
    ) -> str:
        """Read a file from TrueNAS via websocket core.download.

        Uses the already-authenticated websocket connection to request a
        download URL (which includes a token), then fetches the file via HTTP.

        Args:
            path: Absolute path to the file on TrueNAS.
            tail_lines: If > 0, return only the last N lines.
        """
        import httpx

        normalized = os.path.normpath(path)
        allowed_prefixes = ("/var/log/", "/mnt/")
        if not any(normalized.startswith(p) for p in allowed_prefixes):
            raise ValueError(
                f"Path must be under one of: {', '.join(allowed_prefixes)}"
            )

        # Step 1: Use websocket to get a tokenized download URL
        result = await self._call(
            "core.download", "filesystem.get", [normalized], "file.log"
        )

        # core.download returns [job_id, download_url]
        if not isinstance(result, (list, tuple)) or len(result) < 2:
            raise TrueNASAPIError(f"Unexpected core.download response: {result}")

        download_path = result[1]

        # Step 2: Download the file (URL includes auth token, no creds needed)
        scheme = "https" if self.protocol == "wss" else "http"
        download_url = f"{scheme}://{self.host}:{self.port}{download_path}"

        async with httpx.AsyncClient(verify=self.ssl_verify, timeout=30) as client:
            file_resp = await client.get(download_url)

        if file_resp.status_code != 200:
            raise TrueNASAPIError(
                f"Failed to download file ({file_resp.status_code}): {file_resp.text[:200]}"
            )

        content = file_resp.text

        if tail_lines > 0:
            lines = content.splitlines()
            content = "\n".join(lines[-tail_lines:])

        return content

    async def write_file(
        self,
        path: str,
        content: str,
        mode: str = "0644",
    ) -> int:
        """Write a file to TrueNAS via the HTTP /_upload endpoint.

        Mirrors :meth:`read_file`: the websocket connection mints a one-shot
        auth token, then the bytes are POSTed to ``/_upload`` which runs the
        ``filesystem.put`` job server-side. Restricted to ``/mnt/`` so it can
        only touch user data, not system paths.

        Args:
            path: Absolute destination path (must be under /mnt/).
            content: File contents to write.
            mode: Octal permission string applied to the file.

        Returns:
            Number of bytes written.
        """
        import json

        import httpx

        normalized = os.path.normpath(path)
        if not normalized.startswith("/mnt/"):
            raise ValueError("Path must be under /mnt/")

        data = content.encode() if isinstance(content, str) else content
        # filesystem.put expects an integer (octal) mode, not a string.
        mode_int = int(mode, 8) if isinstance(mode, str) else int(mode)

        # One-shot token authorises the stateless HTTP upload request.
        token = await self._call("auth.generate_token", 600, {}, True)

        scheme = "https" if self.protocol == "wss" else "http"
        upload_url = f"{scheme}://{self.host}:{self.port}/_upload"
        payload = json.dumps(
            {"method": "filesystem.put", "params": [normalized, {"mode": mode_int}]}
        )
        files = {
            "data": (None, payload),
            "file": ("file", data, "application/octet-stream"),
        }

        def _upload():
            return httpx.post(
                upload_url,
                files=files,
                headers={"Authorization": f"Token {token}"},
                verify=self.ssl_verify,
                timeout=60,
            )

        resp = await self._run_sync(_upload)

        if resp.status_code not in (200, 201):
            raise TrueNASAPIError(
                f"Upload failed ({resp.status_code}): {resp.text[:200]}"
            )

        # The POST only *queues* a filesystem.put job; wait for it to finish so
        # a failed write raises instead of silently returning a byte count.
        try:
            job_id = resp.json().get("job_id")
        except (ValueError, AttributeError):
            job_id = None
        if job_id is not None:
            await self._call("core.job_wait", job_id, job=True)

        return len(data)

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

    async def create_dataset(
        self,
        name: str,
        compression: Optional[str] = None,
        recordsize: Optional[str] = None,
        quota: Optional[int] = None,
        atime: Optional[str] = None,
        share_type: Optional[str] = None,
        comments: Optional[str] = None,
        create_ancestors: bool = False,
    ) -> Dict[str, Any]:
        """Create a filesystem dataset.

        Only FILESYSTEM datasets are supported. Zvols take a different shape
        (volsize, volblocksize, sparse) and belong with the VM tooling.

        Unset options are omitted rather than sent as null, so the dataset
        inherits from its parent the way the UI would leave it.
        """
        if "/" not in name:
            raise ValueError(
                f"Cannot create '{name}': that is a pool name, not a dataset. "
                "Datasets must be given in pool/dataset form (e.g. 'Services/uptime-kuma'). "
                "Pools are created from the TrueNAS UI."
            )

        payload: Dict[str, Any] = {"name": name, "type": "FILESYSTEM"}
        if compression is not None:
            payload["compression"] = compression
        if recordsize is not None:
            payload["recordsize"] = recordsize
        if quota is not None:
            payload["quota"] = quota
        if atime is not None:
            payload["atime"] = atime
        if share_type is not None:
            payload["share_type"] = share_type
        if comments is not None:
            payload["comments"] = comments
        if create_ancestors:
            payload["create_ancestors"] = True

        return await self._call("pool.dataset.create", payload)

    async def update_dataset(
        self,
        name: str,
        compression: Optional[str] = None,
        recordsize: Optional[str] = None,
        quota: Optional[int] = None,
        refquota: Optional[int] = None,
        atime: Optional[str] = None,
        readonly: Optional[str] = None,
        sync: Optional[str] = None,
        comments: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Change properties on an existing dataset.

        Unlike create/delete this accepts a pool root dataset, since setting a
        property at the pool root so children inherit it is legitimate.

        Returns the updated dataset plus the set of properties that were asked
        for, so the caller can report which ones actually take effect now.
        """
        requested = {
            "compression": compression,
            "recordsize": recordsize,
            "quota": quota,
            "refquota": refquota,
            "atime": atime,
            "readonly": readonly,
            "sync": sync,
            "comments": comments,
        }
        payload = {k: v for k, v in requested.items() if v is not None}

        if not payload:
            raise ValueError(
                f"No properties given for '{name}'. "
                "Pass at least one of: " + ", ".join(sorted(requested))
            )

        matches = await self._call("pool.dataset.query", [["id", "=", name]])
        if not matches:
            raise ValueError(f"Dataset '{name}' does not exist")

        updated = await self._call("pool.dataset.update", name, payload)
        return {"dataset": updated, "requested": sorted(payload)}

    async def delete_dataset(
        self,
        name: str,
        recursive: bool = False,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Destroy a ZFS dataset, irreversibly.

        Unlike delete_snapshot this surfaces the API error rather than
        collapsing it to False: the usual failures ("dataset is busy", "has
        children") are the whole diagnosis, and a bare False throws them away.

        Returns a summary of what was destroyed so the caller can report it.
        """
        if "/" not in name:
            raise ValueError(
                f"Refusing to delete '{name}': that is a pool root dataset. "
                "Datasets must be given in pool/dataset form (e.g. 'Services/coder'). "
                "Destroy a pool from the TrueNAS UI, not from here."
            )

        # Confirm it exists and capture its size before it goes.
        matches = await self._call("pool.dataset.query", [["id", "=", name]])
        if not matches:
            raise ValueError(f"Dataset '{name}' does not exist")
        dataset = matches[0]
        used = int(dataset.get("used", {}).get("rawvalue", 0) or 0)

        children = await self._call("pool.dataset.query", [["id", "^", f"{name}/"]])
        snapshots = await self._call("zfs.snapshot.query", [["dataset", "=", name]])

        # The middleware would reject this anyway, but its error does not say
        # which children are in the way.
        if children and not recursive:
            child_names = ", ".join(sorted(c["id"] for c in children))
            raise ValueError(
                f"Dataset '{name}' has {len(children)} child dataset(s) and "
                f"recursive is not set: {child_names}. "
                "Pass recursive=true to destroy them along with the parent."
            )

        await self._call(
            "pool.dataset.delete",
            name,
            {"recursive": recursive, "force": force},
        )

        return {
            "name": name,
            "used_bytes": used,
            "children_destroyed": [c["id"] for c in children],
            "snapshots_destroyed": len(snapshots),
            "recursive": recursive,
            "force": force,
        }

    # ── NFS Share Tools ───────────────────────────────────────────────

    # Fields the create/update tools expose. `aliases` is documented "IGNORED,
    # for now" by the middleware itself, `expose_snapshots` needs an Enterprise
    # licence, and `security` only means anything with Kerberos configured, so
    # all three are left out rather than offered and quietly ineffective.
    _NFS_LIST_FIELDS = ("hosts", "networks")

    def _validate_nfs_path(self, path: str) -> str:
        """Check an export path is a mountpoint, not a dataset name."""
        path = path.rstrip("/") or "/"

        if not path.startswith("/mnt/"):
            suggestion = f"/mnt/{path.lstrip('/')}"
            raise ValueError(
                f"NFS export path must be a mountpoint under /mnt, got '{path}'. "
                f"Every other tool here takes a dataset name like 'Store/Media', "
                f"but a share takes the mountpoint, so this is probably "
                f"'{suggestion}'."
            )

        return path

    async def _nfs_service_running(self) -> Optional[bool]:
        """Whether the NFS service is up, or None if that could not be read.

        A share on a stopped service exports nothing, and the client sees
        "connection refused" rather than anything mentioning the share, so this
        is worth reporting alongside a successful create.
        """
        try:
            services = await self._call("service.query", [["service", "=", "nfs"]])
        except TrueNASAPIError:
            return None
        if not services:
            return None
        return services[0].get("state") == "RUNNING"

    async def list_nfs_shares(
        self,
        path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List NFS shares, optionally filtered by exported path."""
        if path:
            return await self._call(
                "sharing.nfs.query",
                [["path", "=", path.rstrip("/")]],
            )
        return await self._call("sharing.nfs.query")

    async def _resolve_nfs_share(
        self,
        share_id: Optional[int] = None,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Find exactly one NFS share by id or by exported path."""
        if (share_id is None) == (path is None):
            raise ValueError(
                "Pass exactly one of 'id' or 'path' to identify the share. "
                "Call list_nfs_shares to see both."
            )

        if share_id is not None:
            matches = await self._call("sharing.nfs.query", [["id", "=", share_id]])
            if not matches:
                raise ValueError(
                    f"No NFS share with id {share_id}. "
                    "Call list_nfs_shares to see the current ids."
                )
            return matches[0]

        wanted = path.rstrip("/")
        matches = await self._call("sharing.nfs.query", [["path", "=", wanted]])
        if not matches:
            raise ValueError(
                f"No NFS share exports '{wanted}'. "
                "Call list_nfs_shares to see what is exported."
            )
        return matches[0]

    async def create_nfs_share(
        self,
        path: str,
        hosts: Optional[List[str]] = None,
        networks: Optional[List[str]] = None,
        comment: Optional[str] = None,
        ro: bool = False,
        maproot_user: Optional[str] = None,
        maproot_group: Optional[str] = None,
        mapall_user: Optional[str] = None,
        mapall_group: Optional[str] = None,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Export a path over NFS.

        Returns the created share plus the context needed to report it
        honestly: whether the NFS service is actually running, and whether the
        export ended up open to every host on the network.
        """
        path = self._validate_nfs_path(path)

        # maproot and mapall are mutually exclusive. The middleware rejects the
        # combination, but its error does not explain that they are two answers
        # to the same question.
        if (maproot_user or maproot_group) and (mapall_user or mapall_group):
            raise ValueError(
                "maproot_* and mapall_* cannot both be set: maproot remaps only "
                "the client's root user, mapall remaps every user. Choose one."
            )

        existing = await self._call("sharing.nfs.query", [["path", "=", path]])
        if existing:
            raise ValueError(
                f"'{path}' is already exported by NFS share id {existing[0]['id']}. "
                "Use update_nfs_share to change it rather than creating a second "
                "export of the same path."
            )

        payload: Dict[str, Any] = {"path": path, "ro": ro, "enabled": enabled}
        if hosts:
            payload["hosts"] = hosts
        if networks:
            payload["networks"] = networks
        if comment is not None:
            payload["comment"] = comment
        if maproot_user is not None:
            payload["maproot_user"] = maproot_user
        if maproot_group is not None:
            payload["maproot_group"] = maproot_group
        if mapall_user is not None:
            payload["mapall_user"] = mapall_user
        if mapall_group is not None:
            payload["mapall_group"] = mapall_group

        share = await self._call("sharing.nfs.create", payload)

        return {
            "share": share,
            "service_running": await self._nfs_service_running(),
            "unrestricted": not hosts and not networks,
        }

    async def update_nfs_share(
        self,
        share_id: Optional[int] = None,
        path: Optional[str] = None,
        new_path: Optional[str] = None,
        hosts: Optional[List[str]] = None,
        networks: Optional[List[str]] = None,
        comment: Optional[str] = None,
        ro: Optional[bool] = None,
        maproot_user: Optional[str] = None,
        maproot_group: Optional[str] = None,
        mapall_user: Optional[str] = None,
        mapall_group: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Change an existing NFS share.

        `hosts` and `networks` REPLACE the stored lists rather than adding to
        them, so the before and after of both are returned: passing one new
        client IP would otherwise silently revoke every existing one.
        """
        share = await self._resolve_nfs_share(share_id, path)

        requested = {
            "path": self._validate_nfs_path(new_path) if new_path else None,
            "hosts": hosts,
            "networks": networks,
            "comment": comment,
            "ro": ro,
            "maproot_user": maproot_user,
            "maproot_group": maproot_group,
            "mapall_user": mapall_user,
            "mapall_group": mapall_group,
            "enabled": enabled,
        }
        payload = {k: v for k, v in requested.items() if v is not None}

        if not payload:
            raise ValueError(
                f"No changes given for NFS share id {share['id']}. "
                "Pass at least one of: " + ", ".join(sorted(requested))
            )

        # The same either/or as create, but checked against the merged result:
        # setting mapall on a share that already has maproot is the way this
        # goes wrong in practice.
        merged = {**share, **payload}
        if (merged.get("maproot_user") or merged.get("maproot_group")) and (
            merged.get("mapall_user") or merged.get("mapall_group")
        ):
            raise ValueError(
                f"NFS share id {share['id']} would end up with both maproot_* and "
                "mapall_* set, which the middleware rejects. Clear one by passing "
                "it as an empty string."
            )

        updated = await self._call("sharing.nfs.update", share["id"], payload)

        # Only report a list as changed if it actually moved, so an update that
        # passes hosts unchanged does not read as a revocation.
        replaced = {
            field: {"before": share.get(field) or [], "after": updated.get(field) or []}
            for field in self._NFS_LIST_FIELDS
            if field in payload
            and (share.get(field) or []) != (updated.get(field) or [])
        }

        return {
            "share": updated,
            "requested": sorted(payload),
            "replaced_lists": replaced,
            "unrestricted": not (updated.get("hosts") or updated.get("networks")),
        }

    async def delete_nfs_share(
        self,
        share_id: Optional[int] = None,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Remove an NFS export.

        This unexports a path; it does not touch the data underneath. Returns
        the share as it was so the caller can report, and recreate, what went.
        """
        share = await self._resolve_nfs_share(share_id, path)
        await self._call("sharing.nfs.delete", share["id"])
        return {
            "id": share["id"],
            "path": share.get("path"),
            "hosts": share.get("hosts") or [],
            "networks": share.get("networks") or [],
            "comment": share.get("comment") or "",
        }

    # ── Virtual Machine Management ───────────────────────────────────

    async def create_vm(
        self,
        name: str,
        vcpus: int = 1,
        memory: int = 1024,
        description: str = "",
        autostart: bool = False,
        bootloader: str = "UEFI",
    ) -> Dict[str, Any]:
        """Create a new virtual machine.

        Creates the VM configuration only. Disks, NICs, and displays
        must be added separately via add_vm_device or the TrueNAS UI.

        Args:
            name: VM name.
            vcpus: Number of virtual CPUs.
            memory: Memory in MiB.
            description: Optional description.
            autostart: Start VM on system boot.
            bootloader: UEFI or UEFI_CSM.
        """
        return await self._call("vm.create", {
            "name": name,
            "vcpus": vcpus,
            "memory": memory,
            "description": description,
            "autostart": autostart,
            "bootloader": bootloader,
        })

    async def add_vm_device(
        self, vm_id: int, dtype: str, attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add a device to a virtual machine.

        Args:
            vm_id: The VM ID.
            dtype: Device type — DISK, NIC, DISPLAY, CDROM.
            attributes: Device-specific attributes.
        """
        attributes["dtype"] = dtype
        return await self._call("vm.device.create", {
            "vm": vm_id,
            "attributes": attributes,
        })

    async def query_vm_devices(self, vm_id: int) -> List[Dict[str, Any]]:
        """Query all devices attached to a VM."""
        return await self._call("vm.device.query", [["vm", "=", vm_id]])

    async def update_vm_device(
        self, device_id: int, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a VM device configuration."""
        return await self._call("vm.device.update", device_id, updates)

    async def list_vms(self) -> List[Dict[str, Any]]:
        """List all virtual machines."""
        return await self._call("vm.query")

    async def get_vm_status(self, vm_id: int) -> Dict[str, Any]:
        """Get VM details by ID."""
        vms = await self._call("vm.query", [["id", "=", vm_id]])
        if not vms:
            raise TrueNASAPIError(f"VM with id {vm_id} not found")
        return vms[0]

    async def start_vm(self, vm_id: int) -> bool:
        """Start a virtual machine."""
        try:
            await self._call("vm.start", vm_id)
            return True
        except TrueNASAPIError:
            return False

    async def stop_vm(
        self, vm_id: int, force: bool = False, force_after_timeout: bool = False
    ) -> bool:
        """Stop a virtual machine.

        Args:
            vm_id: The VM ID.
            force: Immediately power off.
            force_after_timeout: Try graceful shutdown, then force after timeout.
        """
        try:
            options = {}
            if force:
                options["force"] = True
            if force_after_timeout:
                options["force_after_timeout"] = True
            await self._call("vm.stop", vm_id, options if options else {})
            return True
        except TrueNASAPIError:
            return False

    async def poweroff_vm(self, vm_id: int) -> bool:
        """Hard power-off a virtual machine (like pulling the power cable)."""
        try:
            await self._call("vm.poweroff", vm_id)
            return True
        except TrueNASAPIError:
            return False

    async def delete_vm(
        self, vm_id: int, delete_zvols: bool = False, force: bool = False
    ) -> bool:
        """Delete a virtual machine.

        Args:
            vm_id: The VM ID.
            delete_zvols: Also delete associated zvol disk images.
            force: Force-stop the VM first if it is running.
        """
        try:
            await self._call("vm.delete", vm_id, {
                "zvols": delete_zvols,
                "force": force,
            })
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
