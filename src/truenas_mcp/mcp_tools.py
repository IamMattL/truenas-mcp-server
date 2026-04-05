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

            # ── Docker Compose Config Tools ───────────────────────────
            Tool(
                name="get_compose_config",
                description="Get the stored Docker Compose YAML for a Custom App (services, volumes, networks)",
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
                name="update_compose_config",
                description="Update the Docker Compose YAML for a Custom App (replaces the entire compose config)",
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
                        "compose_yaml": {
                            "type": "string",
                            "minLength": 10,
                            "maxLength": 100000,
                            "description": "New Docker Compose YAML content",
                        },
                    },
                    "required": ["app_name", "compose_yaml"],
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

            Tool(
                name="read_file",
                description="Read a file from TrueNAS (restricted to /var/log/ and /mnt/)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute file path on TrueNAS (must be under /var/log/ or /mnt/)",
                        },
                        "tail_lines": {
                            "type": "integer",
                            "default": 0,
                            "description": "If > 0, return only the last N lines",
                        },
                    },
                    "required": ["path"],
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

            # ── Virtual Machine Management ────────────────────────────
            Tool(
                name="create_vm",
                description="Create a new virtual machine. Optionally creates disk, NIC, and display to make it bootable.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Name for the virtual machine",
                        },
                        "vcpus": {
                            "type": "integer",
                            "minimum": 1,
                            "default": 1,
                            "description": "Number of virtual CPUs",
                        },
                        "memory": {
                            "type": "integer",
                            "minimum": 256,
                            "default": 1024,
                            "description": "Memory in MiB",
                        },
                        "description": {
                            "type": "string",
                            "default": "",
                            "description": "Optional description",
                        },
                        "autostart": {
                            "type": "boolean",
                            "default": False,
                            "description": "Start VM automatically on system boot",
                        },
                        "bootloader": {
                            "type": "string",
                            "enum": ["UEFI", "UEFI_CSM"],
                            "default": "UEFI",
                            "description": "Bootloader type",
                        },
                        "disk_size_gb": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Disk size in GB — creates a zvol automatically (e.g. 20 for 20GB)",
                        },
                        "disk_zvol_parent": {
                            "type": "string",
                            "default": "Store",
                            "description": "Parent dataset for the zvol (e.g. 'Store' creates Store/vm-name)",
                        },
                        "disk_type": {
                            "type": "string",
                            "enum": ["VIRTIO", "AHCI"],
                            "default": "VIRTIO",
                            "description": "Disk interface type (AHCI for Windows without virtio drivers)",
                        },
                        "nic_attach": {
                            "type": "string",
                            "description": "Host network interface to attach NIC to (e.g. 'enp2s0', 'br0'). Omit to skip NIC.",
                        },
                        "nic_type": {
                            "type": "string",
                            "enum": ["VIRTIO", "E1000"],
                            "default": "VIRTIO",
                            "description": "NIC type (E1000 for Windows without virtio drivers)",
                        },
                        "display_type": {
                            "type": "string",
                            "enum": ["VNC", "SPICE"],
                            "description": "Display type for console access. Omit to skip display.",
                        },
                        "display_password": {
                            "type": "string",
                            "description": "Password for display access (required by TrueNAS). Auto-generated if not provided.",
                        },
                        "iso_path": {
                            "type": "string",
                            "description": "Path to ISO file for CDROM (e.g. '/mnt/Store/ISOs/ubuntu.iso'). Omit to skip.",
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="add_vm_device",
                description="Add a device (disk, NIC, display, CDROM) to an existing VM",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "vm_id": {
                            "type": "integer",
                            "description": "ID of the virtual machine",
                        },
                        "device_type": {
                            "type": "string",
                            "enum": ["DISK", "NIC", "DISPLAY", "CDROM"],
                            "description": "Type of device to add",
                        },
                        "disk_size_gb": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Disk size in GB (DISK only — creates a zvol)",
                        },
                        "disk_zvol_parent": {
                            "type": "string",
                            "default": "Store",
                            "description": "Parent dataset for zvol (DISK only, e.g. 'Store')",
                        },
                        "disk_path": {
                            "type": "string",
                            "description": "Path to existing zvol or disk image (DISK only — alternative to disk_size_gb)",
                        },
                        "nic_attach": {
                            "type": "string",
                            "description": "Host interface to attach to (NIC only, e.g. 'enp2s0')",
                        },
                        "nic_type": {
                            "type": "string",
                            "enum": ["VIRTIO", "E1000"],
                            "default": "VIRTIO",
                            "description": "NIC type (NIC only)",
                        },
                        "display_type": {
                            "type": "string",
                            "enum": ["VNC", "SPICE"],
                            "default": "SPICE",
                            "description": "Display protocol (DISPLAY only)",
                        },
                        "display_bind": {
                            "type": "string",
                            "default": "0.0.0.0",
                            "description": "IP to bind display to (DISPLAY only)",
                        },
                        "display_password": {
                            "type": "string",
                            "description": "Password for display access (DISPLAY only, auto-generated if omitted)",
                        },
                        "iso_path": {
                            "type": "string",
                            "description": "Path to ISO file (CDROM only, e.g. '/mnt/Store/ISOs/ubuntu.iso')",
                        },
                    },
                    "required": ["vm_id", "device_type"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="query_vm_devices",
                description="List all devices attached to a VM with their IDs and order",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "vm_id": {
                            "description": "ID of the virtual machine",
                        }
                    },
                    "required": ["vm_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="update_vm_device",
                description="Update a VM device configuration (e.g. change boot order)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "description": "ID of the device to update",
                        },
                        "order": {
                            "description": "Boot order (lower boots first, e.g. 1001)",
                        },
                    },
                    "required": ["device_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="list_vms",
                description="List all virtual machines with status information",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="get_vm_status",
                description="Get detailed status and configuration for a specific VM",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "vm_id": {
                            "type": "integer",
                            "description": "ID of the virtual machine",
                        }
                    },
                    "required": ["vm_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="start_vm",
                description="Start a virtual machine",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "vm_id": {
                            "type": "integer",
                            "description": "ID of the virtual machine to start",
                        }
                    },
                    "required": ["vm_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="stop_vm",
                description="Stop a virtual machine (graceful ACPI shutdown)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "vm_id": {
                            "type": "integer",
                            "description": "ID of the virtual machine to stop",
                        },
                        "force": {
                            "type": "boolean",
                            "default": False,
                            "description": "Force immediate power off",
                        },
                        "force_after_timeout": {
                            "type": "boolean",
                            "default": False,
                            "description": "Try graceful shutdown, then force after timeout",
                        },
                    },
                    "required": ["vm_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="poweroff_vm",
                description="Hard power-off a VM (use when stop fails — like pulling the power cable)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "vm_id": {
                            "type": "integer",
                            "description": "ID of the virtual machine to power off",
                        }
                    },
                    "required": ["vm_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="delete_vm",
                description="Delete a virtual machine (must confirm deletion)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "vm_id": {
                            "type": "integer",
                            "description": "ID of the virtual machine to delete",
                        },
                        "delete_zvols": {
                            "type": "boolean",
                            "default": False,
                            "description": "Also delete associated zvol disk images",
                        },
                        "force": {
                            "type": "boolean",
                            "default": False,
                            "description": "Force-stop the VM first if running",
                        },
                        "confirm_deletion": {
                            "type": "boolean",
                            "description": "Must be true to confirm deletion",
                        },
                    },
                    "required": ["vm_id", "confirm_deletion"],
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

            # Docker Compose Config Tools
            elif name == "get_compose_config":
                return await self._get_compose_config(arguments["app_name"])

            elif name == "update_compose_config":
                return await self._update_compose_config(
                    app_name=arguments["app_name"],
                    compose_yaml=arguments["compose_yaml"],
                )

            # Filesystem Tools
            elif name == "list_directory":
                return await self._list_directory(
                    path=arguments.get("path", "/mnt"),
                    include_hidden=arguments.get("include_hidden", False),
                )

            elif name == "read_file":
                return await self._read_file(
                    path=arguments["path"],
                    tail_lines=arguments.get("tail_lines", 0),
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

            # Virtual Machine Management
            elif name == "create_vm":
                return await self._create_vm(
                    name=arguments["name"],
                    vcpus=arguments.get("vcpus", 1),
                    memory=arguments.get("memory", 1024),
                    description=arguments.get("description", ""),
                    autostart=arguments.get("autostart", False),
                    bootloader=arguments.get("bootloader", "UEFI"),
                    disk_size_gb=arguments.get("disk_size_gb"),
                    disk_zvol_parent=arguments.get("disk_zvol_parent", "Store"),
                    disk_type=arguments.get("disk_type", "VIRTIO"),
                    nic_attach=arguments.get("nic_attach"),
                    nic_type=arguments.get("nic_type", "VIRTIO"),
                    display_type=arguments.get("display_type"),
                    display_password=arguments.get("display_password"),
                    iso_path=arguments.get("iso_path"),
                )

            elif name == "add_vm_device":
                return await self._add_vm_device(arguments)

            elif name == "query_vm_devices":
                return await self._query_vm_devices(int(arguments["vm_id"]))

            elif name == "update_vm_device":
                return await self._update_vm_device(
                    device_id=int(arguments["device_id"]),
                    order=int(arguments["order"]) if arguments.get("order") is not None else None,
                )

            elif name == "list_vms":
                return await self._list_vms()

            elif name == "get_vm_status":
                return await self._get_vm_status(arguments["vm_id"])

            elif name == "start_vm":
                return await self._start_vm(arguments["vm_id"])

            elif name == "stop_vm":
                return await self._stop_vm(
                    vm_id=arguments["vm_id"],
                    force=arguments.get("force", False),
                    force_after_timeout=arguments.get("force_after_timeout", False),
                )

            elif name == "poweroff_vm":
                return await self._poweroff_vm(arguments["vm_id"])

            elif name == "delete_vm":
                return await self._delete_vm(
                    vm_id=arguments["vm_id"],
                    delete_zvols=arguments.get("delete_zvols", False),
                    force=arguments.get("force", False),
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
        error = await self.client.deploy_app(app_name, compose_yaml, auto_start)
        if error is None:
            return TextContent(
                type="text",
                text=f"✅ Deployed Custom App '{app_name}' successfully"
            )
        else:
            return TextContent(
                type="text",
                text=f"❌ Failed to deploy Custom App '{app_name}': {error}"
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

    # ── Docker Compose Config Handlers ───────────────────────────────

    async def _get_compose_config(self, app_name: str) -> TextContent:
        """Get the stored Docker Compose config as YAML."""
        import yaml

        config = await self.client.get_compose_config(app_name)

        if not config:
            return TextContent(
                type="text",
                text=f"No compose config found for '{app_name}'",
            )

        yaml_str = yaml.dump(config, default_flow_style=False, sort_keys=False)
        return TextContent(
            type="text",
            text=f"Docker Compose config for '{app_name}':\n\n```yaml\n{yaml_str}```",
        )

    async def _update_compose_config(
        self,
        app_name: str,
        compose_yaml: str,
    ) -> TextContent:
        """Update the Docker Compose config from a YAML string."""
        success = await self.client.update_compose_config(app_name, compose_yaml)
        if success:
            return TextContent(
                type="text",
                text=f"✅ Updated Docker Compose config for '{app_name}'",
            )
        else:
            return TextContent(
                type="text",
                text=f"❌ Failed to update Docker Compose config for '{app_name}'",
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

    async def _read_file(
        self,
        path: str,
        tail_lines: int = 0,
    ) -> TextContent:
        """Read a file from TrueNAS."""
        content = await self.client.read_file(path, tail_lines)
        header = f"File: {path}"
        if tail_lines > 0:
            header += f" (last {tail_lines} lines)"
        return TextContent(type="text", text=f"{header}\n\n{content}")

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

    # ── Virtual Machine Handlers ─────────────────────────────────────

    async def _create_vm(
        self,
        name: str,
        vcpus: int,
        memory: int,
        description: str,
        autostart: bool,
        bootloader: str,
        disk_size_gb: Optional[int] = None,
        disk_zvol_parent: str = "Store",
        disk_type: str = "VIRTIO",
        nic_attach: Optional[str] = None,
        nic_type: str = "VIRTIO",
        display_type: Optional[str] = None,
        display_password: Optional[str] = None,
        iso_path: Optional[str] = None,
    ) -> TextContent:
        """Create a new VM, optionally with devices for bootability."""
        result = await self.client.create_vm(
            name=name,
            vcpus=vcpus,
            memory=memory,
            description=description,
            autostart=autostart,
            bootloader=bootloader,
        )
        vm_id = result.get("id", "?")
        lines = [
            f"✅ Created VM '{name}' (ID: {vm_id})",
            f"  vCPUs: {vcpus}, Memory: {memory} MiB, Bootloader: {bootloader}",
        ]

        devices_added = []

        # Add disk (zvol)
        if disk_size_gb:
            zvol_name = f"{disk_zvol_parent}/vms/{name}"
            zvol_size = disk_size_gb * 1024 * 1024 * 1024
            try:
                # Ensure parent dataset exists
                parent_ds = f"{disk_zvol_parent}/vms"
                try:
                    await self.client._call("pool.dataset.create", {
                        "name": parent_ds,
                    })
                    devices_added.append(f"  + Created dataset '{parent_ds}'")
                except Exception:
                    pass  # Already exists, that's fine

                await self.client.add_vm_device(vm_id, "DISK", {
                    "create_zvol": True,
                    "zvol_name": zvol_name,
                    "zvol_volsize": zvol_size,
                    "type": disk_type,
                })
                devices_added.append(f"  + DISK: {zvol_name} ({disk_size_gb} GB, {disk_type})")
            except Exception as e:
                devices_added.append(f"  ! DISK failed: {e}")

        # Add NIC
        if nic_attach:
            try:
                await self.client.add_vm_device(vm_id, "NIC", {
                    "type": nic_type,
                    "nic_attach": nic_attach,
                })
                devices_added.append(f"  + NIC: {nic_type} on {nic_attach}")
            except Exception as e:
                devices_added.append(f"  ! NIC failed: {e}")

        # Add display
        if display_type:
            import secrets
            password = display_password or secrets.token_urlsafe(12)
            try:
                await self.client.add_vm_device(vm_id, "DISPLAY", {
                    "type": display_type,
                    "bind": "0.0.0.0",
                    "password": password,
                    "web": True,
                })
                devices_added.append(f"  + DISPLAY: {display_type} (web enabled, password: {password})")
            except Exception as e:
                devices_added.append(f"  ! DISPLAY failed: {e}")

        # Add CDROM (ISO)
        if iso_path:
            try:
                await self.client.add_vm_device(vm_id, "CDROM", {
                    "path": iso_path,
                })
                devices_added.append(f"  + CDROM: {iso_path}")
            except Exception as e:
                devices_added.append(f"  ! CDROM failed: {e}")

        if devices_added:
            lines.append("\n  Devices:")
            lines.extend(devices_added)
        else:
            lines.append("  Note: No devices added — add disk, NIC, and display before starting.")

        return TextContent(type="text", text="\n".join(lines))

    async def _add_vm_device(self, arguments: Dict[str, Any]) -> TextContent:
        """Add a device to an existing VM."""
        vm_id = arguments["vm_id"]
        dtype = arguments["device_type"]
        attrs: Dict[str, Any] = {}

        if dtype == "DISK":
            if arguments.get("disk_path"):
                attrs["path"] = arguments["disk_path"]
                attrs["type"] = "VIRTIO"
            elif arguments.get("disk_size_gb"):
                # Need VM name for zvol naming — fetch it
                vm = await self.client.get_vm_status(vm_id)
                vm_name = vm.get("name", f"vm-{vm_id}")
                parent = arguments.get("disk_zvol_parent", "Store")
                attrs["create_zvol"] = True
                attrs["zvol_name"] = f"{parent}/vms/{vm_name}"
                attrs["zvol_volsize"] = arguments["disk_size_gb"] * 1024 * 1024 * 1024
                attrs["type"] = "VIRTIO"
            else:
                return TextContent(
                    type="text",
                    text="❌ DISK requires either disk_size_gb (to create zvol) or disk_path (existing disk)",
                )

        elif dtype == "NIC":
            attrs["type"] = arguments.get("nic_type", "VIRTIO")
            if arguments.get("nic_attach"):
                attrs["nic_attach"] = arguments["nic_attach"]

        elif dtype == "DISPLAY":
            import secrets
            attrs["type"] = arguments.get("display_type", "SPICE")
            attrs["bind"] = arguments.get("display_bind", "0.0.0.0")
            attrs["password"] = arguments.get("display_password") or secrets.token_urlsafe(12)
            attrs["web"] = True

        elif dtype == "CDROM":
            if not arguments.get("iso_path"):
                return TextContent(
                    type="text",
                    text="❌ CDROM requires iso_path",
                )
            attrs["path"] = arguments["iso_path"]

        result = await self.client.add_vm_device(vm_id, dtype, attrs)
        device_id = result.get("id", "?")
        return TextContent(
            type="text",
            text=f"✅ Added {dtype} device (ID: {device_id}) to VM {vm_id}",
        )

    async def _query_vm_devices(self, vm_id: int) -> TextContent:
        """Query all devices attached to a VM."""
        devices = await self.client.query_vm_devices(vm_id)

        if not devices:
            return TextContent(type="text", text=f"No devices found for VM {vm_id}")

        lines = [f"Devices for VM {vm_id}\n"]
        lines.append(f"{'ID':<6} {'Type':<10} {'Order':<7} Details")
        lines.append("-" * 60)
        for dev in devices:
            dev_id = dev.get("id", "?")
            attrs = dev.get("attributes", {})
            dtype = attrs.get("dtype", dev.get("dtype", "?"))
            order = dev.get("order", "?")

            if dtype == "DISK":
                detail = attrs.get("path", attrs.get("zvol_name", "?"))
            elif dtype == "NIC":
                detail = f"{attrs.get('type', '?')} on {attrs.get('nic_attach', '?')}"
            elif dtype == "DISPLAY":
                detail = f"{attrs.get('type', '?')} bind:{attrs.get('bind', '?')}"
            elif dtype == "CDROM":
                detail = attrs.get("path", "?")
            else:
                detail = str(attrs)[:50]

            lines.append(f"{dev_id:<6} {dtype:<10} {str(order):<7} {detail}")

        return TextContent(type="text", text="\n".join(lines))

    async def _update_vm_device(
        self, device_id: int, order: Optional[int] = None
    ) -> TextContent:
        """Update a VM device."""
        updates = {}
        if order is not None:
            updates["order"] = order

        if not updates:
            return TextContent(type="text", text="❌ No updates specified")

        await self.client.update_vm_device(device_id, updates)
        return TextContent(
            type="text",
            text=f"✅ Updated device {device_id} (order: {order})",
        )

    async def _list_vms(self) -> TextContent:
        """List all virtual machines."""
        vms = await self.client.list_vms()

        if not vms:
            return TextContent(type="text", text="No virtual machines found")

        lines = ["Virtual Machines\n"]
        lines.append(f"{'ID':<5} {'Name':<25} {'State':<12} {'vCPUs':>5} {'Memory':>10}  Description")
        lines.append("-" * 80)
        for vm in vms:
            vm_id = vm.get("id", "?")
            name = vm.get("name", "?")
            status = vm.get("status", {})
            state = status.get("state", "UNKNOWN") if isinstance(status, dict) else "UNKNOWN"
            vcpus = vm.get("vcpus", "?")
            mem_bytes = (vm.get("memory") or 0) * 1024 * 1024  # memory is in MiB
            mem_str = _format_bytes(mem_bytes)
            desc = vm.get("description", "")[:30]
            lines.append(f"{vm_id:<5} {name:<25} {state:<12} {vcpus:>5} {mem_str:>10}  {desc}")

        return TextContent(type="text", text="\n".join(lines))

    async def _get_vm_status(self, vm_id: int) -> TextContent:
        """Get detailed VM status."""
        vm = await self.client.get_vm_status(vm_id)

        status = vm.get("status", {})
        state = status.get("state", "UNKNOWN") if isinstance(status, dict) else "UNKNOWN"
        pid = status.get("pid") if isinstance(status, dict) else None

        lines = [
            f"VM '{vm.get('name', '?')}' (ID: {vm_id})\n",
            f"  State       : {state}",
            f"  vCPUs       : {vm.get('vcpus', '?')}",
            f"  Memory      : {vm.get('memory', '?')} MiB",
            f"  Autostart   : {vm.get('autostart', False)}",
            f"  Bootloader  : {vm.get('bootloader', '?')}",
            f"  Description : {vm.get('description', '-')}",
        ]

        if pid:
            lines.append(f"  PID         : {pid}")

        # Show devices if present
        devices = vm.get("devices", [])
        if devices:
            lines.append(f"\n  Devices ({len(devices)}):")
            for dev in devices:
                attrs = dev.get("attributes", {})
                dtype = attrs.get("dtype", dev.get("dtype", "?"))
                order = dev.get("order", "?")
                if dtype == "DISK":
                    lines.append(f"    - DISK: {attrs.get('path', '?')} (order: {order})")
                elif dtype == "NIC":
                    lines.append(f"    - NIC: {attrs.get('type', '?')} ({attrs.get('nic_attach', '?')})")
                elif dtype == "DISPLAY":
                    lines.append(f"    - DISPLAY: {attrs.get('type', '?')} port {attrs.get('port', '?')}")
                elif dtype == "CDROM":
                    lines.append(f"    - CDROM: {attrs.get('path', '?')} (order: {order})")
                else:
                    lines.append(f"    - {dtype}")

        return TextContent(type="text", text="\n".join(lines))

    async def _start_vm(self, vm_id: int) -> TextContent:
        """Start a VM."""
        success = await self.client.start_vm(vm_id)
        if success:
            return TextContent(type="text", text=f"✅ Started VM {vm_id}")
        else:
            return TextContent(type="text", text=f"❌ Failed to start VM {vm_id}")

    async def _stop_vm(
        self, vm_id: int, force: bool, force_after_timeout: bool
    ) -> TextContent:
        """Stop a VM."""
        success = await self.client.stop_vm(vm_id, force, force_after_timeout)
        mode = "force" if force else ("force-after-timeout" if force_after_timeout else "graceful")
        if success:
            return TextContent(type="text", text=f"✅ Stop signal sent to VM {vm_id} ({mode})")
        else:
            return TextContent(type="text", text=f"❌ Failed to stop VM {vm_id}")

    async def _poweroff_vm(self, vm_id: int) -> TextContent:
        """Hard power-off a VM."""
        success = await self.client.poweroff_vm(vm_id)
        if success:
            return TextContent(type="text", text=f"✅ Powered off VM {vm_id}")
        else:
            return TextContent(type="text", text=f"❌ Failed to power off VM {vm_id}")

    async def _delete_vm(
        self,
        vm_id: int,
        delete_zvols: bool,
        force: bool,
        confirm_deletion: bool,
    ) -> TextContent:
        """Delete a VM."""
        if not confirm_deletion:
            return TextContent(
                type="text",
                text="❌ Deletion not confirmed. Set confirm_deletion=true to proceed.",
            )

        success = await self.client.delete_vm(vm_id, delete_zvols, force)
        extras = []
        if delete_zvols:
            extras.append("zvols deleted")
        if force:
            extras.append("force-stopped")
        extra_str = f" ({', '.join(extras)})" if extras else ""

        if success:
            return TextContent(
                type="text",
                text=f"✅ Deleted VM {vm_id}{extra_str}",
            )
        else:
            return TextContent(
                type="text",
                text=f"❌ Failed to delete VM {vm_id}",
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