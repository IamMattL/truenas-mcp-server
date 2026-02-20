"""MCP Tools implementation for TrueNAS Scale Custom Apps."""

from typing import Any, Dict, List, Optional

import structlog
from mcp.types import TextContent, Tool

from .truenas_client import TrueNASClient

logger = structlog.get_logger(__name__)


def _format_bytes(num_bytes: int) -> str:
    """Format byte count into human-readable string."""
    if num_bytes is None:
        num_bytes = 0
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PiB"


class MCPToolsHandler:
    """Handler for all MCP tools."""

    def __init__(self, truenas_client: Optional[TrueNASClient]) -> None:
        """Initialize tools handler. Client can be None for static tool listing."""
        self.client = truenas_client

    async def list_tools(self) -> List[Tool]:
        """List all available MCP tools."""
        return [
            # Connection Management
            Tool(
                name="test_connection",
                description="Test TrueNAS API connectivity and authentication",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            
            # Custom App Management
            Tool(
                name="list_custom_apps",
                description="List all Custom Apps with status information",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "status_filter": {
                            "type": "string",
                            "enum": ["running", "stopped", "error", "all"],
                            "default": "all",
                            "description": "Filter apps by status",
                        }
                    },
                    "additionalProperties": False,
                },
            ),
            
            Tool(
                name="get_custom_app_status",
                description="Get detailed status information for a specific Custom App",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$",
                            "minLength": 2,
                            "maxLength": 50,
                            "description": "Name of the Custom App",
                        }
                    },
                    "required": ["app_name"],
                    "additionalProperties": False,
                },
            ),
            
            Tool(
                name="get_custom_app_config",
                description="Get full configuration of a Custom App (image, ports, env vars, volumes, metadata)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$",
                            "minLength": 2,
                            "maxLength": 50,
                            "description": "Name of the Custom App",
                        }
                    },
                    "required": ["app_name"],
                    "additionalProperties": False,
                },
            ),

            Tool(
                name="start_custom_app",
                description="Start a stopped Custom App",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$",
                            "description": "Name of the Custom App to start",
                        }
                    },
                    "required": ["app_name"],
                    "additionalProperties": False,
                },
            ),
            
            Tool(
                name="stop_custom_app",
                description="Stop a running Custom App",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$",
                            "description": "Name of the Custom App to stop",
                        }
                    },
                    "required": ["app_name"],
                    "additionalProperties": False,
                },
            ),
            
            # Deployment Tools
            Tool(
                name="deploy_custom_app",
                description="Deploy a new Custom App from Docker Compose configuration",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$",
                            "minLength": 2,
                            "maxLength": 50,
                            "description": "Unique name for the Custom App",
                        },
                        "compose_yaml": {
                            "type": "string",
                            "minLength": 10,
                            "maxLength": 100000,
                            "description": "Docker Compose YAML content",
                        },
                        "auto_start": {
                            "type": "boolean",
                            "default": True,
                            "description": "Whether to start the app after deployment",
                        },
                    },
                    "required": ["app_name", "compose_yaml"],
                    "additionalProperties": False,
                },
            ),
            
            Tool(
                name="update_custom_app",
                description="Update an existing Custom App with new Docker Compose configuration",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$",
                            "description": "Name of the Custom App to update",
                        },
                        "compose_yaml": {
                            "type": "string",
                            "minLength": 10,
                            "maxLength": 100000,
                            "description": "New Docker Compose YAML content",
                        },
                        "force_recreate": {
                            "type": "boolean",
                            "default": False,
                            "description": "Force recreation of containers",
                        },
                    },
                    "required": ["app_name", "compose_yaml"],
                    "additionalProperties": False,
                },
            ),
            
            Tool(
                name="update_custom_app_config",
                description="Update specific configuration fields of a Custom App without requiring full Docker Compose YAML",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$",
                            "minLength": 2,
                            "maxLength": 50,
                            "description": "Name of the Custom App to update",
                        },
                        "config": {
                            "type": "object",
                            "description": "Configuration fields to update (e.g. environment variables, image, ports)",
                        },
                    },
                    "required": ["app_name", "config"],
                    "additionalProperties": False,
                },
            ),

            Tool(
                name="delete_custom_app",
                description="Delete a Custom App and optionally its data volumes",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$",
                            "description": "Name of the Custom App to delete",
                        },
                        "delete_volumes": {
                            "type": "boolean",
                            "default": False,
                            "description": "Whether to delete associated data volumes",
                        },
                        "confirm_deletion": {
                            "type": "boolean",
                            "description": "Safety confirmation for destructive operation",
                        },
                    },
                    "required": ["app_name", "confirm_deletion"],
                    "additionalProperties": False,
                },
            ),
            
            # Validation Tools
            Tool(
                name="validate_compose",
                description="Validate Docker Compose YAML for TrueNAS compatibility",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "compose_yaml": {
                            "type": "string",
                            "minLength": 10,
                            "maxLength": 100000,
                            "description": "Docker Compose YAML to validate",
                        },
                        "check_security": {
                            "type": "boolean",
                            "default": True,
                            "description": "Whether to perform security validation",
                        },
                    },
                    "required": ["compose_yaml"],
                    "additionalProperties": False,
                },
            ),
            
            Tool(
                name="get_app_logs",
                description="Retrieve logs from a Custom App",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$",
                            "description": "Name of the Custom App",
                        },
                        "lines": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 1000,
                            "default": 100,
                            "description": "Number of log lines to retrieve",
                        },
                        "service_name": {
                            "type": "string",
                            "description": "Specific service within the app (optional)",
                        },
                    },
                    "required": ["app_name"],
                    "additionalProperties": False,
                },
            ),

            # ── Filesystem Tools ──────────────────────────────────────
            Tool(
                name="list_directory",
                description="Browse filesystem contents on TrueNAS (restricted to /mnt/)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "default": "/mnt",
                            "description": "Directory path to list (must be under /mnt/)",
                        },
                        "include_hidden": {
                            "type": "boolean",
                            "default": False,
                            "description": "Include hidden files/directories (starting with .)",
                        },
                    },
                    "additionalProperties": False,
                },
            ),

            # ── ZFS Dataset / Snapshot Tools ──────────────────────────
            Tool(
                name="list_datasets",
                description="List ZFS datasets with usage information",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pool_name": {
                            "type": "string",
                            "description": "Filter datasets by pool name (optional)",
                        },
                    },
                    "additionalProperties": False,
                },
            ),

            Tool(
                name="list_snapshots",
                description="List ZFS snapshots with size information",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "dataset": {
                            "type": "string",
                            "description": "Filter snapshots by dataset (optional)",
                        },
                    },
                    "additionalProperties": False,
                },
            ),

            Tool(
                name="create_snapshot",
                description="Create a ZFS snapshot for backup or rollback",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "dataset": {
                            "type": "string",
                            "description": "Dataset to snapshot (e.g. 'Store/Media')",
                        },
                        "name": {
                            "type": "string",
                            "description": "Snapshot name (e.g. 'pre-upgrade-20260218')",
                        },
                        "recursive": {
                            "type": "boolean",
                            "default": False,
                            "description": "Include child datasets in the snapshot",
                        },
                    },
                    "required": ["dataset", "name"],
                    "additionalProperties": False,
                },
            ),

            Tool(
                name="delete_snapshot",
                description="Delete a ZFS snapshot",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "snapshot_name": {
                            "type": "string",
                            "description": "Full snapshot name (e.g. 'Store/Media@snap1')",
                        },
                        "confirm_deletion": {
                            "type": "boolean",
                            "description": "Safety confirmation for destructive operation",
                        },
                    },
                    "required": ["snapshot_name", "confirm_deletion"],
                    "additionalProperties": False,
                },
            ),

            # ── System / Pool / Network Info ──────────────────────────
            Tool(
                name="get_system_info",
                description="Get TrueNAS system information (hostname, version, uptime, CPU, RAM)",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),

            Tool(
                name="get_storage_pools",
                description="Get storage pool health, capacity, and scrub status",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),

            Tool(
                name="get_network_info",
                description="Get network interface information (IPs, link state, speed)",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> TextContent:
        """Execute an MCP tool by name."""
        logger.info("Executing MCP tool", tool=name, args=arguments)
        
        try:
            # Connection Management Tools
            if name == "test_connection":
                return await self._test_connection()
            
            # Custom App Management Tools
            elif name == "list_custom_apps":
                return await self._list_custom_apps(
                    status_filter=arguments.get("status_filter", "all")
                )
            
            elif name == "get_custom_app_status":
                return await self._get_custom_app_status(arguments["app_name"])

            elif name == "get_custom_app_config":
                return await self._get_custom_app_config(arguments["app_name"])

            elif name == "start_custom_app":
                return await self._start_custom_app(arguments["app_name"])
            
            elif name == "stop_custom_app":
                return await self._stop_custom_app(arguments["app_name"])
            
            # Deployment Tools
            elif name == "deploy_custom_app":
                return await self._deploy_custom_app(
                    app_name=arguments["app_name"],
                    compose_yaml=arguments["compose_yaml"],
                    auto_start=arguments.get("auto_start", True),
                )
            
            elif name == "update_custom_app":
                return await self._update_custom_app(
                    app_name=arguments["app_name"],
                    compose_yaml=arguments["compose_yaml"],
                    force_recreate=arguments.get("force_recreate", False),
                )

            elif name == "update_custom_app_config":
                return await self._update_custom_app_config(
                    app_name=arguments["app_name"],
                    config=arguments["config"],
                )

            elif name == "delete_custom_app":
                return await self._delete_custom_app(
                    app_name=arguments["app_name"],
                    delete_volumes=arguments.get("delete_volumes", False),
                    confirm_deletion=arguments["confirm_deletion"],
                )
            
            # Validation Tools
            elif name == "validate_compose":
                return await self._validate_compose(
                    compose_yaml=arguments["compose_yaml"],
                    check_security=arguments.get("check_security", True),
                )
            
            elif name == "get_app_logs":
                return await self._get_app_logs(
                    app_name=arguments["app_name"],
                    lines=arguments.get("lines", 100),
                    service_name=arguments.get("service_name"),
                )

            # Filesystem Tools
            elif name == "list_directory":
                return await self._list_directory(
                    path=arguments.get("path", "/mnt"),
                    include_hidden=arguments.get("include_hidden", False),
                )

            # ZFS Dataset / Snapshot Tools
            elif name == "list_datasets":
                return await self._list_datasets(
                    pool_name=arguments.get("pool_name"),
                )

            elif name == "list_snapshots":
                return await self._list_snapshots(
                    dataset=arguments.get("dataset"),
                )

            elif name == "create_snapshot":
                return await self._create_snapshot(
                    dataset=arguments["dataset"],
                    name=arguments["name"],
                    recursive=arguments.get("recursive", False),
                )

            elif name == "delete_snapshot":
                return await self._delete_snapshot(
                    snapshot_name=arguments["snapshot_name"],
                    confirm_deletion=arguments["confirm_deletion"],
                )

            # System / Pool / Network Info
            elif name == "get_system_info":
                return await self._get_system_info()

            elif name == "get_storage_pools":
                return await self._get_storage_pools()

            elif name == "get_network_info":
                return await self._get_network_info()

            else:
                raise ValueError(f"Unknown tool: {name}")
                
        except Exception as e:
            logger.error("Tool execution failed", tool=name, error=str(e), exc_info=True)
            return TextContent(
                type="text",
                text=f"❌ Error executing {name}: {str(e)}"
            )

    # Tool Implementation Methods (Stubs for now)
    
    async def _test_connection(self) -> TextContent:
        """Test TrueNAS connection."""
        success = await self.client.test_connection()
        if success:
            return TextContent(
                type="text",
                text="✅ TrueNAS connection successful"
            )
        else:
            return TextContent(
                type="text",
                text="❌ TrueNAS connection failed"
            )
    
    async def _list_custom_apps(self, status_filter: str) -> TextContent:
        """List Custom Apps."""
        apps = await self.client.list_custom_apps(status_filter)
        if not apps:
            return TextContent(
                type="text",
                text="No Custom Apps found"
            )
        
        result = "Custom Apps:\n"
        for app in apps:
            state = app.get("state", "unknown")
            result += f"- {app['name']}: {state}\n"
        
        return TextContent(type="text", text=result)
    
    async def _get_custom_app_status(self, app_name: str) -> TextContent:
        """Get Custom App status."""
        status = await self.client.get_app_status(app_name)
        return TextContent(
            type="text",
            text=f"App '{app_name}' status: {status}"
        )
    
    async def _get_custom_app_config(self, app_name: str) -> TextContent:
        """Get full Custom App configuration."""
        app_data = await self.client.get_app_config(app_name)

        lines = [f"Configuration for '{app_name}':\n"]

        # State, version, and type
        lines.append(f"  State   : {app_data.get('state', 'unknown')}")
        if app_data.get("version"):
            lines.append(f"  Version : {app_data['version']}")
        if app_data.get("human_version"):
            lines.append(f"  App ver : {app_data['human_version']}")
        if app_data.get("custom_app") is not None:
            lines.append(f"  Type    : {'Custom App' if app_data['custom_app'] else 'Catalog App'}")
        if app_data.get("upgrade_available"):
            lines.append(f"  Upgrade : available (latest: {app_data.get('latest_version', '?')})")

        # Mock data path: config.services (used in tests)
        config = app_data.get("config") or {}
        mock_services = config.get("services") or {} if isinstance(config, dict) else {}

        if mock_services:
            lines.append("\n  Services:")
            for svc_name, svc in mock_services.items():
                if not isinstance(svc, dict):
                    continue
                lines.append(f"\n    [{svc_name}]")
                lines.append(f"      Image   : {svc.get('image', '?')}")
                network = svc.get("network") or {}
                ports = network.get("ports") or []
                if ports:
                    port_strs = [
                        f"{p['host']}:{p['container']}/{p.get('protocol', 'tcp')}"
                        for p in ports if isinstance(p, dict)
                    ]
                    lines.append(f"      Ports   : {', '.join(port_strs)}")
                if network.get("host_network"):
                    lines.append("      Network : host")
                env = svc.get("environment") or {}
                if env:
                    lines.append("      Env vars:")
                    for k, v in env.items():
                        lines.append(f"        {k}={v}")
                storage = svc.get("storage") or []
                if storage:
                    lines.append("      Volumes:")
                    for vol in storage:
                        if not isinstance(vol, dict):
                            continue
                        ro = " (ro)" if vol.get("read_only") else ""
                        lines.append(f"        {vol.get('host_path', '?')} -> {vol.get('mount_path', '?')}{ro}")
                if svc.get("restart_policy"):
                    lines.append(f"      Restart : {svc['restart_policy']}")

        # Real TrueNAS API path: active_workloads.container_details
        workloads = app_data.get("active_workloads") or {}
        container_details = workloads.get("container_details") or []

        if not mock_services and container_details:
            lines.append(f"\n  Containers: {len(container_details)}")
            for ctr in container_details:
                if not isinstance(ctr, dict):
                    continue
                svc_name = ctr.get("service_name", "?")
                lines.append(f"\n    [{svc_name}]")
                lines.append(f"      Image   : {ctr.get('image', '?')}")
                lines.append(f"      State   : {ctr.get('state', '?')}")

                # Ports from port_config
                port_config = ctr.get("port_config") or []
                if port_config:
                    port_strs = []
                    for pc in port_config:
                        if not isinstance(pc, dict):
                            continue
                        cport = pc.get("container_port", "?")
                        proto = pc.get("protocol", "tcp")
                        for hp in pc.get("host_ports") or []:
                            if isinstance(hp, dict):
                                hport = hp.get("host_port", "?")
                                hip = hp.get("host_ip", "")
                                if hip and hip not in ("0.0.0.0", "::"):
                                    port_strs.append(f"{hip}:{hport}:{cport}/{proto}")
                                else:
                                    port_strs.append(f"{hport}:{cport}/{proto}")
                                break  # One host port per container port is enough
                    if port_strs:
                        lines.append(f"      Ports   : {', '.join(port_strs)}")

                # Volume mounts
                vol_mounts = ctr.get("volume_mounts") or []
                if vol_mounts:
                    lines.append("      Volumes:")
                    for vm in vol_mounts:
                        if not isinstance(vm, dict):
                            continue
                        src = vm.get("source", "?")
                        dst = vm.get("destination", "?")
                        mode = f" ({vm['mode']})" if vm.get("mode") else ""
                        lines.append(f"        {src} -> {dst}{mode}")

        # Images list from workloads (useful even if no container_details)
        images = workloads.get("images") or []
        if not mock_services and not container_details and images:
            lines.append(f"\n  Images: {', '.join(images)}")

        # Container count summary when no details available
        if not mock_services and not container_details:
            container_count = workloads.get("containers", 0)
            if container_count:
                lines.append(f"\n  Active workloads: {container_count} container(s)")

        # Portals
        portals = app_data.get("portals") or {}
        if isinstance(portals, dict) and portals:
            lines.append("\n  Portals:")
            for portal_name, portal_url in portals.items():
                lines.append(f"    {portal_name}: {portal_url}")

        # Notes
        notes = app_data.get("notes") or ""
        if notes:
            lines.append(f"\n  Notes: {notes[:200]}{'...' if len(notes) > 200 else ''}")

        # Metadata
        metadata = app_data.get("metadata") or {}
        if isinstance(metadata, dict) and metadata:
            lines.append("\n  Metadata:")
            for k, v in metadata.items():
                lines.append(f"    {k}: {v}")

        return TextContent(type="text", text="\n".join(lines))

    async def _update_custom_app_config(
        self,
        app_name: str,
        config: Dict[str, Any],
    ) -> TextContent:
        """Update Custom App configuration."""
        success = await self.client.update_app_config(app_name, config)
        if success:
            changed_keys = ", ".join(config.keys())
            return TextContent(
                type="text",
                text=f"✅ Updated config for '{app_name}' (changed: {changed_keys})",
            )
        else:
            return TextContent(
                type="text",
                text=f"❌ Failed to update config for '{app_name}'",
            )

    async def _start_custom_app(self, app_name: str) -> TextContent:
        """Start Custom App."""
        success = await self.client.start_app(app_name)
        if success:
            return TextContent(
                type="text",
                text=f"✅ Started Custom App '{app_name}'"
            )
        else:
            return TextContent(
                type="text",
                text=f"❌ Failed to start Custom App '{app_name}'"
            )
    
    async def _stop_custom_app(self, app_name: str) -> TextContent:
        """Stop Custom App."""
        success = await self.client.stop_app(app_name)
        if success:
            return TextContent(
                type="text",
                text=f"✅ Stopped Custom App '{app_name}'"
            )
        else:
            return TextContent(
                type="text",
                text=f"❌ Failed to stop Custom App '{app_name}'"
            )
    
    async def _deploy_custom_app(
        self,
        app_name: str,
        compose_yaml: str,
        auto_start: bool,
    ) -> TextContent:
        """Deploy Custom App."""
        success = await self.client.deploy_app(app_name, compose_yaml, auto_start)
        if success:
            return TextContent(
                type="text",
                text=f"✅ Deployed Custom App '{app_name}' successfully"
            )
        else:
            return TextContent(
                type="text",
                text=f"❌ Failed to deploy Custom App '{app_name}'"
            )
    
    async def _update_custom_app(
        self,
        app_name: str,
        compose_yaml: str,
        force_recreate: bool,
    ) -> TextContent:
        """Update Custom App."""
        success = await self.client.update_app(app_name, compose_yaml, force_recreate)
        if success:
            return TextContent(
                type="text",
                text=f"✅ Updated Custom App '{app_name}' successfully"
            )
        else:
            return TextContent(
                type="text",
                text=f"❌ Failed to update Custom App '{app_name}'"
            )
    
    async def _delete_custom_app(
        self,
        app_name: str,
        delete_volumes: bool,
        confirm_deletion: bool,
    ) -> TextContent:
        """Delete Custom App."""
        if not confirm_deletion:
            return TextContent(
                type="text",
                text="❌ Deletion not confirmed. Set confirm_deletion=true to proceed."
            )
        
        success = await self.client.delete_app(app_name, delete_volumes)
        if success:
            return TextContent(
                type="text",
                text=f"✅ Deleted Custom App '{app_name}' successfully"
            )
        else:
            return TextContent(
                type="text",
                text=f"❌ Failed to delete Custom App '{app_name}'"
            )
    
    async def _validate_compose(
        self,
        compose_yaml: str,
        check_security: bool,
    ) -> TextContent:
        """Validate Docker Compose."""
        is_valid, issues = await self.client.validate_compose(compose_yaml, check_security)
        
        if is_valid and not issues:
            return TextContent(
                type="text",
                text="✅ Docker Compose is valid and secure"
            )
        elif is_valid and issues:
            warnings = "\n".join([f"⚠️ {issue}" for issue in issues])
            return TextContent(
                type="text",
                text=f"✅ Docker Compose is valid but has warnings:\n{warnings}"
            )
        else:
            errors = "\n".join([f"❌ {issue}" for issue in issues])
            return TextContent(
                type="text",
                text=f"❌ Docker Compose validation failed:\n{errors}"
            )
    
    async def _get_app_logs(
        self,
        app_name: str,
        lines: int,
        service_name: Optional[str],
    ) -> TextContent:
        """Get Custom App logs."""
        logs = await self.client.get_app_logs(app_name, lines, service_name)

        if logs:
            return TextContent(
                type="text",
                text=f"Logs for '{app_name}':\n{logs}"
            )
        else:
            return TextContent(
                type="text",
                text=f"No logs found for '{app_name}'"
            )

    # ── Filesystem Handler ────────────────────────────────────────────

    async def _list_directory(
        self,
        path: str,
        include_hidden: bool,
    ) -> TextContent:
        """List directory contents."""
        entries = await self.client.list_directory(path, include_hidden)

        if not entries:
            return TextContent(type="text", text=f"Directory '{path}' is empty")

        # Sort: directories first, then files, alphabetical within each
        dirs = sorted(
            [e for e in entries if e.get("type") == "DIRECTORY"],
            key=lambda e: e["name"],
        )
        files = sorted(
            [e for e in entries if e.get("type") != "DIRECTORY"],
            key=lambda e: e["name"],
        )

        lines = [f"Directory: {path}\n"]
        lines.append(f"{'Type':<6} {'Size':>10}  Name")
        lines.append("-" * 40)
        for entry in dirs + files:
            etype = "DIR" if entry.get("type") == "DIRECTORY" else "FILE"
            size = _format_bytes(entry.get("size", 0)) if etype == "FILE" else "-"
            lines.append(f"{etype:<6} {size:>10}  {entry['name']}")

        return TextContent(type="text", text="\n".join(lines))

    # ── ZFS Dataset / Snapshot Handlers ───────────────────────────────

    async def _list_datasets(
        self,
        pool_name: Optional[str],
    ) -> TextContent:
        """List ZFS datasets."""
        datasets = await self.client.list_datasets(pool_name)

        if not datasets:
            return TextContent(type="text", text="No datasets found")

        header = "ZFS Datasets"
        if pool_name:
            header += f" (pool: {pool_name})"

        lines = [f"{header}\n"]
        lines.append(f"{'Dataset':<30} {'Used':>10} {'Available':>10}  Mountpoint")
        lines.append("-" * 75)
        for ds in datasets:
            name = ds.get("name", ds.get("id", "?"))
            used = _format_bytes(int(ds.get("used", {}).get("rawvalue", 0)))
            avail = _format_bytes(int(ds.get("available", {}).get("rawvalue", 0)))
            mount = ds.get("mountpoint", "-")
            lines.append(f"{name:<30} {used:>10} {avail:>10}  {mount}")

        return TextContent(type="text", text="\n".join(lines))

    async def _list_snapshots(
        self,
        dataset: Optional[str],
    ) -> TextContent:
        """List ZFS snapshots."""
        snapshots = await self.client.list_snapshots(dataset)

        if not snapshots:
            label = f" for '{dataset}'" if dataset else ""
            return TextContent(type="text", text=f"No snapshots found{label}")

        header = "ZFS Snapshots"
        if dataset:
            header += f" (dataset: {dataset})"

        lines = [f"{header}\n"]
        for snap in snapshots:
            name = snap.get("name", "?")
            props = snap.get("properties", {})
            used = _format_bytes(int(props.get("used", {}).get("rawvalue", 0)))
            ref = _format_bytes(int(props.get("referenced", {}).get("rawvalue", 0)))
            lines.append(f"  - {name}  (used: {used}, referenced: {ref})")

        return TextContent(type="text", text="\n".join(lines))

    async def _create_snapshot(
        self,
        dataset: str,
        name: str,
        recursive: bool,
    ) -> TextContent:
        """Create a ZFS snapshot."""
        result = await self.client.create_snapshot(dataset, name, recursive)
        snap_name = result.get("name", f"{dataset}@{name}")
        extra = " (recursive)" if recursive else ""
        return TextContent(
            type="text",
            text=f"✅ Created snapshot '{snap_name}'{extra}",
        )

    async def _delete_snapshot(
        self,
        snapshot_name: str,
        confirm_deletion: bool,
    ) -> TextContent:
        """Delete a ZFS snapshot."""
        if not confirm_deletion:
            return TextContent(
                type="text",
                text="❌ Deletion not confirmed. Set confirm_deletion=true to proceed.",
            )

        success = await self.client.delete_snapshot(snapshot_name)
        if success:
            return TextContent(
                type="text",
                text=f"✅ Deleted snapshot '{snapshot_name}'",
            )
        else:
            return TextContent(
                type="text",
                text=f"❌ Failed to delete snapshot '{snapshot_name}'",
            )

    # ── System / Pool / Network Handlers ──────────────────────────────

    async def _get_system_info(self) -> TextContent:
        """Get TrueNAS system information."""
        info = await self.client.get_system_info()

        uptime_s = info.get("uptime_seconds", 0)
        days = int(uptime_s // 86400)
        hours = int((uptime_s % 86400) // 3600)
        minutes = int((uptime_s % 3600) // 60)

        mem_bytes = info.get("physmem", 0)

        lines = [
            "TrueNAS System Info\n",
            f"  Hostname : {info.get('hostname', '?')}",
            f"  Version  : {info.get('version', '?')}",
            f"  Uptime   : {days}d {hours}h {minutes}m",
            f"  CPU      : {info.get('model', '?')} ({info.get('cores', '?')} cores)",
            f"  Memory   : {_format_bytes(mem_bytes)}",
            f"  Load Avg : {info.get('loadavg', [])}",
        ]

        return TextContent(type="text", text="\n".join(lines))

    async def _get_storage_pools(self) -> TextContent:
        """Get storage pool information."""
        pools = await self.client.get_storage_pools()

        if not pools:
            return TextContent(type="text", text="No storage pools found")

        lines = ["Storage Pools\n"]
        for pool in pools:
            name = pool.get("name", "?")
            status = pool.get("status", "?")
            healthy = "YES" if pool.get("healthy") else "NO"
            size = _format_bytes(pool.get("size") or 0)
            alloc = _format_bytes(pool.get("allocated") or 0)
            free = _format_bytes(pool.get("free") or 0)

            # Topology type from first data vdev
            topo = pool.get("topology", {}).get("data", [{}])
            vdev_type = topo[0].get("type", "?") if topo else "?"

            # Scrub info
            scan = pool.get("scan", {})
            scrub_state = scan.get("state", "UNKNOWN")
            scrub_errors = scan.get("errors", "?")

            lines.append(f"  [{name}]")
            lines.append(f"    Status  : {status} (healthy: {healthy})")
            lines.append(f"    Layout  : {vdev_type}")
            lines.append(f"    Size    : {size}  (allocated: {alloc}, free: {free})")
            lines.append(f"    Scrub   : {scrub_state} (errors: {scrub_errors})")
            lines.append("")

        return TextContent(type="text", text="\n".join(lines))

    async def _get_network_info(self) -> TextContent:
        """Get network interface information."""
        interfaces = await self.client.get_network_info()

        if not interfaces:
            return TextContent(type="text", text="No network interfaces found")

        lines = ["Network Interfaces\n"]
        for iface in interfaces:
            name = iface.get("name", "?")
            itype = iface.get("type", "?")
            state_info = iface.get("state", {})
            link = state_info.get("link_state", "?")
            mtu = state_info.get("mtu", "?")
            speed = state_info.get("speed")
            speed_str = f"{speed} Mbps" if speed else "-"

            aliases = iface.get("aliases", [])
            ips = [
                f"{a['address']}/{a.get('netmask', '')}"
                for a in aliases
                if a.get("type") == "INET"
            ]

            lines.append(f"  [{name}] ({itype})")
            lines.append(f"    Link  : {link}")
            lines.append(f"    MTU   : {mtu}")
            lines.append(f"    Speed : {speed_str}")
            if ips:
                lines.append(f"    IPs   : {', '.join(ips)}")
            lines.append("")

        return TextContent(type="text", text="\n".join(lines))