"""Docker Compose to TrueNAS Custom App converter."""

import os
import re
from typing import Any, Dict, List

import structlog
import yaml

logger = structlog.get_logger(__name__)

# Max YAML input size (100KB)
MAX_YAML_SIZE = 100 * 1024


class DockerComposeConverter:
    """Converts Docker Compose YAML to TrueNAS Custom App format."""

    async def convert(self, compose_yaml: str, app_name: str) -> Dict[str, Any]:
        """Convert Docker Compose to TrueNAS Custom App configuration.

        Returns a config dict with a 'services' list containing all converted services.
        """
        logger.info("Converting Docker Compose to TrueNAS format", app=app_name)

        if len(compose_yaml.encode("utf-8")) > MAX_YAML_SIZE:
            raise ValueError(
                f"YAML input exceeds maximum size of {MAX_YAML_SIZE} bytes"
            )

        try:
            compose_data = yaml.safe_load(compose_yaml)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}")

        services = compose_data.get("services", {})
        if not services:
            raise ValueError("No services found in Docker Compose")

        converted_services = []
        for service_name, service_config in services.items():
            converted = self._convert_service(service_name, service_config)
            converted_services.append(converted)

        truenas_config = {
            "name": app_name,
            "services": converted_services,
            "restart_policy": "unless-stopped",
        }

        return truenas_config

    def _convert_service(
        self, service_name: str, service_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert a single Docker Compose service to TrueNAS format."""
        image_str = service_config.get("image", "")

        return {
            "name": service_name,
            "image": {
                "repository": image_str.split(":")[0],
                "tag": (
                    image_str.split(":")[-1]
                    if ":" in image_str
                    else "latest"
                ),
            },
            "network": self._convert_network(service_config),
            "storage": self._convert_storage(service_config),
            "environment": self._convert_environment(service_config),
        }

    def _convert_network(self, service_config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert network configuration."""
        network_config: Dict[str, Any] = {"type": "bridge"}

        ports = service_config.get("ports", [])
        if ports:
            port_forwards = []
            for port in ports:
                parsed = self._parse_port(port)
                if parsed:
                    port_forwards.append(parsed)

            if port_forwards:
                network_config["port_forwards"] = port_forwards

        return network_config

    def _parse_port(self, port: Any) -> Dict[str, Any] | None:
        """Parse a port mapping string or int into a port forward dict.

        Handles formats: "8080:80", "8080:80/udp", 8080 (int)
        """
        if isinstance(port, int):
            return {
                "host_port": port,
                "container_port": port,
                "protocol": "tcp",
            }

        if not isinstance(port, str):
            return None

        if ":" not in port:
            return None

        # Strip protocol suffix (e.g., /udp, /tcp)
        protocol = "tcp"
        port_str = port
        proto_match = re.match(r"^(.+)/(tcp|udp)$", port_str)
        if proto_match:
            port_str = proto_match.group(1)
            protocol = proto_match.group(2)

        parts = port_str.split(":")
        try:
            host_port = int(parts[0])
            container_port = int(parts[1])
        except (ValueError, IndexError):
            logger.warning("Skipping invalid port mapping", port=port)
            return None

        return {
            "host_port": host_port,
            "container_port": container_port,
            "protocol": protocol,
        }

    def _convert_storage(self, service_config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert storage/volumes configuration."""
        storage_config: Dict[str, Any] = {}

        volumes = service_config.get("volumes", [])
        for i, volume in enumerate(volumes):
            if isinstance(volume, str):
                if ":" in volume:
                    host_path, container_path = volume.split(":")[:2]
                    read_only = ":ro" in volume

                    storage_key = f"volume_{i}"
                    # Normalize host path to prevent traversal
                    normalized = os.path.normpath(host_path)
                    if normalized.startswith("/mnt/"):
                        storage_config[storage_key] = {
                            "type": "host_path",
                            "host_path": normalized,
                            "mount_path": container_path,
                            "read_only": read_only,
                        }
                    else:
                        # Named volume -> IX volume
                        # Strip leading underscores/slashes from dataset name
                        dataset_name = host_path.strip("/").replace("/", "_")
                        storage_config[storage_key] = {
                            "type": "ix_volume",
                            "ix_volume_config": {
                                "dataset_name": dataset_name,
                                "acl_enable": False,
                            },
                            "mount_path": container_path,
                        }

        return storage_config

    def _convert_environment(self, service_config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert environment variables."""
        env_config: Dict[str, Any] = {}

        environment = service_config.get("environment", [])
        if isinstance(environment, list):
            for env_var in environment:
                if "=" in env_var:
                    key, value = env_var.split("=", 1)
                    env_config[key] = value
        elif isinstance(environment, dict):
            env_config = environment

        return env_config
