"""Mock TrueNAS client for development and testing."""

import asyncio
import random
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


class MockTrueNASClient:
    """Mock TrueNAS client for development without real TrueNAS access."""

    def __init__(self) -> None:
        """Initialize mock client."""
        self.connected = False
        self.authenticated = False
        
        # Mock data
        # Filesystem mock data
        self.mock_filesystem = {
            "/mnt": [
                {"name": "Store", "type": "DIRECTORY", "size": 0, "mode": 0o755},
                {"name": "Boot", "type": "DIRECTORY", "size": 0, "mode": 0o755},
                {"name": ".zfs", "type": "DIRECTORY", "size": 0, "mode": 0o755},
            ],
            "/mnt/Store": [
                {"name": "Media", "type": "DIRECTORY", "size": 0, "mode": 0o755},
                {"name": "Apps", "type": "DIRECTORY", "size": 0, "mode": 0o755},
                {"name": "Backups", "type": "DIRECTORY", "size": 0, "mode": 0o755},
                {"name": ".config", "type": "DIRECTORY", "size": 0, "mode": 0o755},
            ],
            "/mnt/Store/Media": [
                {"name": "Movies", "type": "DIRECTORY", "size": 0, "mode": 0o755},
                {"name": "TV Shows", "type": "DIRECTORY", "size": 0, "mode": 0o755},
                {"name": "readme.txt", "type": "FILE", "size": 1024, "mode": 0o644},
            ],
        }

        # ZFS dataset mock data
        self.mock_datasets = [
            {
                "id": "Store",
                "pool": "Store",
                "name": "Store",
                "type": "FILESYSTEM",
                "used": {"rawvalue": "5497558138880"},
                "available": {"rawvalue": "10995116277760"},
                "mountpoint": "/mnt/Store",
            },
            {
                "id": "Store/Media",
                "pool": "Store",
                "name": "Store/Media",
                "type": "FILESYSTEM",
                "used": {"rawvalue": "4398046511104"},
                "available": {"rawvalue": "10995116277760"},
                "mountpoint": "/mnt/Store/Media",
            },
            {
                "id": "Store/Apps",
                "pool": "Store",
                "name": "Store/Apps",
                "type": "FILESYSTEM",
                "used": {"rawvalue": "536870912000"},
                "available": {"rawvalue": "10995116277760"},
                "mountpoint": "/mnt/Store/Apps",
            },
            {
                "id": "Boot/ROOT",
                "pool": "Boot",
                "name": "Boot/ROOT",
                "type": "FILESYSTEM",
                "used": {"rawvalue": "21474836480"},
                "available": {"rawvalue": "107374182400"},
                "mountpoint": "/mnt/Boot/ROOT",
            },
        ]

        # ZFS snapshot mock data
        self.mock_snapshots = [
            {
                "name": "Store/Media@pre-tdarr-20260215",
                "dataset": "Store/Media",
                "properties": {
                    "referenced": {"rawvalue": "4398046511104"},
                    "used": {"rawvalue": "1073741824"},
                    "creation": {"rawvalue": "1739577600"},
                },
            },
            {
                "name": "Store/Apps@daily-20260217",
                "dataset": "Store/Apps",
                "properties": {
                    "referenced": {"rawvalue": "536870912000"},
                    "used": {"rawvalue": "52428800"},
                    "creation": {"rawvalue": "1739750400"},
                },
            },
        ]

        # System info mock data
        self.mock_system_info = {
            "hostname": "truenas",
            "version": "TrueNAS-SCALE-24.10.2",
            "uptime_seconds": 864000,
            "cores": 4,
            "physical_cores": 4,
            "loadavg": [0.5, 0.7, 0.6],
            "physmem": 17179869184,
            "model": "Intel(R) Core(TM) i7-7700 CPU @ 3.60GHz",
            "buildtime": {"$date": 1700000000000},
        }

        # Pool mock data
        self.mock_pools = [
            {
                "name": "Store",
                "status": "ONLINE",
                "healthy": True,
                "size": 17592186044416,
                "allocated": 5497558138880,
                "free": 12094627905536,
                "scan": {
                    "function": "SCRUB",
                    "state": "FINISHED",
                    "end_time": {"$date": 1739404800000},
                    "errors": 0,
                },
                "topology": {
                    "data": [{"type": "RAIDZ2", "status": "ONLINE"}],
                },
            },
            {
                "name": "Boot",
                "status": "ONLINE",
                "healthy": True,
                "size": 128849018880,
                "allocated": 21474836480,
                "free": 107374182400,
                "scan": {
                    "function": "SCRUB",
                    "state": "FINISHED",
                    "end_time": {"$date": 1739404800000},
                    "errors": 0,
                },
                "topology": {
                    "data": [{"type": "MIRROR", "status": "ONLINE"}],
                },
            },
        ]

        # Network interface mock data
        self.mock_interfaces = [
            {
                "name": "enp2s0",
                "type": "PHYSICAL",
                "state": {"link_state": "LINK_STATE_UP", "mtu": 1500, "speed": 2500},
                "aliases": [
                    {"type": "INET", "address": "192.168.10.249", "netmask": 24},
                ],
            },
            {
                "name": "lo",
                "type": "LOOPBACK",
                "state": {"link_state": "LINK_STATE_UP", "mtu": 65536, "speed": None},
                "aliases": [
                    {"type": "INET", "address": "127.0.0.1", "netmask": 8},
                ],
            },
        ]

        self.mock_apps = {
            "nginx-demo": {
                "name": "nginx-demo",
                "state": "RUNNING",
                "containers": ["nginx-demo-web-1"],
                "ports": ["8080:80"],
                "created": "2025-07-30T10:00:00Z",
                "version": "1.0.0",
                "config": {
                    "services": {
                        "web": {
                            "image": "nginx:latest",
                            "network": {"host_network": False, "ports": [{"host": 8080, "container": 80, "protocol": "tcp"}]},
                            "storage": [{"host_path": "/mnt/Store/Apps/nginx/html", "mount_path": "/usr/share/nginx/html", "read_only": True}],
                            "environment": {"NGINX_HOST": "localhost", "NGINX_PORT": "80"},
                            "restart_policy": "unless-stopped",
                        }
                    }
                },
                "active_workloads": {"containers": 1, "used_ports": [{"host": 8080, "container": 80}]},
                "metadata": {"app_version": "1.0.0", "train": "custom"},
            },
            "plex-server": {
                "name": "plex-server",
                "state": "STOPPED",
                "containers": ["plex-server-plex-1"],
                "ports": ["32400:32400"],
                "created": "2025-07-29T15:30:00Z",
                "version": "1.41.0",
                "config": {
                    "services": {
                        "plex": {
                            "image": "plexinc/pms-docker:1.41.0",
                            "network": {"host_network": True, "ports": [{"host": 32400, "container": 32400, "protocol": "tcp"}]},
                            "storage": [
                                {"host_path": "/mnt/Store/Apps/plex/config", "mount_path": "/config", "read_only": False},
                                {"host_path": "/mnt/Store/Media", "mount_path": "/media", "read_only": True},
                            ],
                            "environment": {"PLEX_CLAIM": "claim-xxxx", "TZ": "Europe/London"},
                            "restart_policy": "unless-stopped",
                        }
                    }
                },
                "active_workloads": {"containers": 0, "used_ports": []},
                "metadata": {"app_version": "1.41.0", "train": "custom"},
            },
            "home-assistant": {
                "name": "home-assistant",
                "state": "RUNNING",
                "containers": ["home-assistant-hass-1"],
                "ports": ["8123:8123"],
                "created": "2025-07-28T09:15:00Z",
                "version": "2025.1.0",
                "config": {
                    "services": {
                        "hass": {
                            "image": "ghcr.io/home-assistant/home-assistant:2025.1",
                            "network": {"host_network": False, "ports": [{"host": 8123, "container": 8123, "protocol": "tcp"}]},
                            "storage": [{"host_path": "/mnt/Store/Apps/hass/config", "mount_path": "/config", "read_only": False}],
                            "environment": {"TZ": "Europe/London"},
                            "restart_policy": "unless-stopped",
                        }
                    }
                },
                "active_workloads": {"containers": 1, "used_ports": [{"host": 8123, "container": 8123}]},
                "metadata": {"app_version": "2025.1.0", "train": "custom"},
            },
        }

    async def connect(self) -> None:
        """Mock connection to TrueNAS."""
        logger.info("Mock: Connecting to TrueNAS")
        await asyncio.sleep(0.1)  # Simulate connection delay
        self.connected = True
        self.authenticated = True
        logger.info("Mock: Connected and authenticated successfully")

    async def disconnect(self) -> None:
        """Mock disconnection."""
        logger.info("Mock: Disconnecting from TrueNAS")
        self.connected = False
        self.authenticated = False

    async def test_connection(self) -> bool:
        """Mock connection test."""
        logger.info("Mock: Testing connection")
        await asyncio.sleep(0.1)  # Simulate API call
        return True

    async def list_custom_apps(self, status_filter: str = "all") -> List[Dict[str, Any]]:
        """Mock list Custom Apps."""
        logger.info("Mock: Listing Custom Apps", filter=status_filter)
        await asyncio.sleep(0.2)  # Simulate API call
        
        apps = list(self.mock_apps.values())
        
        if status_filter != "all":
            apps = [app for app in apps if app["state"].lower() == status_filter.lower()]
        
        return apps

    async def get_app_status(self, app_name: str) -> str:
        """Mock get Custom App status."""
        logger.info("Mock: Getting app status", app=app_name)
        await asyncio.sleep(0.1)
        
        if app_name not in self.mock_apps:
            raise Exception(f"App '{app_name}' not found")
        
        return self.mock_apps[app_name]["state"]

    async def get_app_config(self, app_name: str) -> Dict[str, Any]:
        """Mock get full Custom App configuration."""
        logger.info("Mock: Getting app config", app=app_name)
        await asyncio.sleep(0.1)

        if app_name not in self.mock_apps:
            raise Exception(f"App '{app_name}' not found")

        return dict(self.mock_apps[app_name])

    async def update_app_config(self, app_name: str, config: Dict[str, Any]) -> bool:
        """Mock update Custom App configuration with raw config dict."""
        logger.info("Mock: Updating app config", app=app_name, keys=list(config.keys()))
        await asyncio.sleep(0.3)

        if app_name not in self.mock_apps:
            return False

        # Merge config into existing app data
        for key, value in config.items():
            if key == "config" and "config" in self.mock_apps[app_name]:
                # Deep-merge the config.services level
                existing = self.mock_apps[app_name]["config"]
                for section, section_val in value.items():
                    if section in existing and isinstance(existing[section], dict) and isinstance(section_val, dict):
                        existing[section].update(section_val)
                    else:
                        existing[section] = section_val
            else:
                self.mock_apps[app_name][key] = value

        return True

    async def start_app(self, app_name: str) -> bool:
        """Mock start Custom App."""
        logger.info("Mock: Starting app", app=app_name)
        await asyncio.sleep(0.5)  # Simulate start time
        
        if app_name not in self.mock_apps:
            return False
        
        self.mock_apps[app_name]["state"] = "RUNNING"
        return True

    async def stop_app(self, app_name: str) -> bool:
        """Mock stop Custom App."""
        logger.info("Mock: Stopping app", app=app_name)
        await asyncio.sleep(0.3)  # Simulate stop time
        
        if app_name not in self.mock_apps:
            return False
        
        self.mock_apps[app_name]["state"] = "STOPPED"
        return True

    async def deploy_app(
        self,
        app_name: str,
        compose_yaml: str,
        auto_start: bool = True,
    ) -> bool:
        """Mock deploy Custom App."""
        logger.info("Mock: Deploying app", app=app_name, auto_start=auto_start)
        await asyncio.sleep(1.0)  # Simulate deployment time
        
        # Add new app to mock data
        self.mock_apps[app_name] = {
            "name": app_name,
            "state": "RUNNING" if auto_start else "STOPPED",
            "containers": [f"{app_name}-service-1"],
            "ports": ["8080:80"],  # Mock port
            "created": "2025-07-30T12:00:00Z",
        }
        return True

    async def update_app(
        self,
        app_name: str,
        compose_yaml: str,
        force_recreate: bool = False,
    ) -> bool:
        """Mock update Custom App."""
        logger.info("Mock: Updating app", app=app_name, force_recreate=force_recreate)
        await asyncio.sleep(0.8)  # Simulate update time
        
        if app_name not in self.mock_apps:
            return False
        
        # Simulate update (always successful in mock)
        logger.info("Mock: App updated successfully")
        return True

    async def delete_app(self, app_name: str, delete_volumes: bool = False) -> bool:
        """Mock delete Custom App."""
        logger.info("Mock: Deleting app", app=app_name, delete_volumes=delete_volumes)
        await asyncio.sleep(0.4)  # Simulate deletion time
        
        if app_name not in self.mock_apps:
            return False
        
        # Remove app from mock data
        del self.mock_apps[app_name]
        return True

    async def validate_compose(
        self,
        compose_yaml: str,
        check_security: bool = True,
    ) -> Tuple[bool, List[str]]:
        """Mock validate Docker Compose."""
        logger.info("Mock: Validating Docker Compose", check_security=check_security)
        await asyncio.sleep(0.2)
        
        issues = []

        # Mock validation logic
        if "version" not in compose_yaml:
            issues.append("Missing version field in Docker Compose")

        if "services" not in compose_yaml:
            issues.append("No services defined in Docker Compose")

        if check_security:
            if "privileged: true" in compose_yaml:
                issues.append("Privileged containers are not allowed")

            if "/etc/" in compose_yaml:
                issues.append("System directory bind mounts are not allowed")

        # Errors are issues without "Warning:" prefix
        errors = [issue for issue in issues if not issue.startswith("Warning:")]
        is_valid = len(errors) == 0

        return is_valid, issues

    async def get_app_logs(
        self,
        app_name: str,
        lines: int = 100,
        service_name: Optional[str] = None,
    ) -> str:
        """Mock get Custom App logs."""
        logger.info("Mock: Getting app logs", app=app_name, lines=lines, service=service_name)
        await asyncio.sleep(0.3)

        if app_name not in self.mock_apps:
            return "App not found"

        # Generate mock logs
        mock_logs = []
        for i in range(min(lines, 20)):  # Limit to 20 lines for mock
            timestamp = f"2025-07-30T12:{30 + i:02d}:{random.randint(10, 59):02d}Z"
            level = random.choice(["INFO", "WARN", "ERROR", "DEBUG"])
            message = random.choice([
                "Service started successfully",
                "Processing request",
                "Database connection established",
                "Configuration loaded",
                "Health check passed",
                "Request completed",
                "Cache updated",
                "Background task finished",
            ])
            mock_logs.append(f"[{timestamp}] {level}: {message}")

        return "\n".join(mock_logs)

    # ── Filesystem Tools ──────────────────────────────────────────────

    async def list_directory(
        self,
        path: str = "/mnt",
        include_hidden: bool = False,
    ) -> List[Dict[str, Any]]:
        """Mock list directory contents."""
        import os
        logger.info("Mock: Listing directory", path=path)
        await asyncio.sleep(0.1)

        normalized = os.path.normpath(path)
        if not normalized.startswith("/mnt"):
            raise ValueError("Path must be under /mnt/")

        entries = self.mock_filesystem.get(normalized, [])
        if not include_hidden:
            entries = [e for e in entries if not e["name"].startswith(".")]
        return entries

    # ── ZFS Dataset / Snapshot Tools ──────────────────────────────────

    async def list_datasets(
        self,
        pool_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Mock list ZFS datasets."""
        logger.info("Mock: Listing datasets", pool=pool_name)
        await asyncio.sleep(0.1)

        if pool_name:
            return [d for d in self.mock_datasets if d["pool"] == pool_name]
        return list(self.mock_datasets)

    async def list_snapshots(
        self,
        dataset: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Mock list ZFS snapshots."""
        logger.info("Mock: Listing snapshots", dataset=dataset)
        await asyncio.sleep(0.1)

        if dataset:
            return [s for s in self.mock_snapshots if s["dataset"] == dataset]
        return list(self.mock_snapshots)

    async def create_snapshot(
        self,
        dataset: str,
        name: str,
        recursive: bool = False,
    ) -> Dict[str, Any]:
        """Mock create ZFS snapshot."""
        logger.info("Mock: Creating snapshot", dataset=dataset, name=name)
        await asyncio.sleep(0.2)

        if "/" not in dataset:
            raise ValueError(
                "Dataset must be in pool/dataset format (e.g. 'Store/Media')"
            )

        snapshot = {
            "name": f"{dataset}@{name}",
            "dataset": dataset,
            "properties": {
                "referenced": {"rawvalue": "0"},
                "used": {"rawvalue": "0"},
                "creation": {"rawvalue": "1739836800"},
            },
        }
        self.mock_snapshots.append(snapshot)
        return snapshot

    async def delete_snapshot(self, snapshot_name: str) -> bool:
        """Mock delete ZFS snapshot."""
        logger.info("Mock: Deleting snapshot", snapshot=snapshot_name)
        await asyncio.sleep(0.2)

        for i, snap in enumerate(self.mock_snapshots):
            if snap["name"] == snapshot_name:
                self.mock_snapshots.pop(i)
                return True
        return False

    # ── System / Pool / Network Info ──────────────────────────────────

    async def get_system_info(self) -> Dict[str, Any]:
        """Mock get system information."""
        logger.info("Mock: Getting system info")
        await asyncio.sleep(0.1)
        return dict(self.mock_system_info)

    async def get_storage_pools(self) -> List[Dict[str, Any]]:
        """Mock get storage pools."""
        logger.info("Mock: Getting storage pools")
        await asyncio.sleep(0.1)
        return list(self.mock_pools)

    async def get_network_info(self) -> List[Dict[str, Any]]:
        """Mock get network interfaces."""
        logger.info("Mock: Getting network info")
        await asyncio.sleep(0.1)
        return list(self.mock_interfaces)