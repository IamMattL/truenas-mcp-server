"""Tests for Docker Compose to TrueNAS converter."""

import pytest
from unittest.mock import AsyncMock

from truenas_mcp.compose_converter import DockerComposeConverter


class TestDockerComposeConverter:
    """Test Docker Compose conversion functionality."""

    @pytest.fixture
    def converter(self):
        """Create converter instance."""
        return DockerComposeConverter()

    @pytest.mark.asyncio
    async def test_basic_conversion(self, converter):
        """Test basic Docker Compose conversion."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx:1.25
    ports:
      - "8080:80"
    environment:
      - NGINX_HOST=localhost
      - NGINX_PORT=80
    volumes:
      - /mnt/pool/nginx/html:/usr/share/nginx/html:ro
      - web_config:/etc/nginx/conf.d
volumes:
  web_config:
"""

        result = await converter.convert(compose_yaml, "nginx-app")

        # Check basic structure
        assert result["name"] == "nginx-app"
        assert "services" in result
        assert len(result["services"]) == 1
        assert result["restart_policy"] == "unless-stopped"

        svc = result["services"][0]
        assert svc["name"] == "web"
        assert svc["image"]["repository"] == "nginx"
        assert svc["image"]["tag"] == "1.25"
        assert "network" in svc
        assert "storage" in svc
        assert "environment" in svc

    @pytest.mark.asyncio
    async def test_image_conversion_no_tag(self, converter):
        """Test image conversion without explicit tag."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx
"""

        result = await converter.convert(compose_yaml, "test-app")

        svc = result["services"][0]
        assert svc["image"]["repository"] == "nginx"
        assert svc["image"]["tag"] == "latest"

    @pytest.mark.asyncio
    async def test_network_conversion_simple_ports(self, converter):
        """Test network conversion with simple port mapping."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx
    ports:
      - "8080:80"
      - "8443:443"
"""

        result = await converter.convert(compose_yaml, "test-app")

        network = result["services"][0]["network"]
        assert network["type"] == "bridge"
        assert "port_forwards" in network

        port_forwards = network["port_forwards"]
        assert len(port_forwards) == 2

        # Check first port mapping
        assert port_forwards[0]["host_port"] == 8080
        assert port_forwards[0]["container_port"] == 80
        assert port_forwards[0]["protocol"] == "tcp"

        # Check second port mapping
        assert port_forwards[1]["host_port"] == 8443
        assert port_forwards[1]["container_port"] == 443
        assert port_forwards[1]["protocol"] == "tcp"

    @pytest.mark.asyncio
    async def test_network_conversion_no_ports(self, converter):
        """Test network conversion without port mappings."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx
"""

        result = await converter.convert(compose_yaml, "test-app")

        network = result["services"][0]["network"]
        assert network["type"] == "bridge"
        assert "port_forwards" not in network

    @pytest.mark.asyncio
    async def test_port_with_protocol(self, converter):
        """Test port parsing with protocol suffix."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx
    ports:
      - "8080:80/udp"
      - "8443:443/tcp"
"""

        result = await converter.convert(compose_yaml, "test-app")

        port_forwards = result["services"][0]["network"]["port_forwards"]
        assert len(port_forwards) == 2
        assert port_forwards[0]["protocol"] == "udp"
        assert port_forwards[1]["protocol"] == "tcp"

    @pytest.mark.asyncio
    async def test_storage_conversion_host_paths(self, converter):
        """Test storage conversion with host path volumes."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx
    volumes:
      - /mnt/pool/data:/var/data
      - /mnt/pool/config:/etc/config:ro
"""

        result = await converter.convert(compose_yaml, "test-app")

        storage = result["services"][0]["storage"]
        assert len(storage) == 2

        # Check first volume
        volume_0 = storage["volume_0"]
        assert volume_0["type"] == "host_path"
        assert volume_0["host_path"] == "/mnt/pool/data"
        assert volume_0["mount_path"] == "/var/data"
        assert volume_0["read_only"] is False

        # Check second volume (read-only)
        volume_1 = storage["volume_1"]
        assert volume_1["type"] == "host_path"
        assert volume_1["host_path"] == "/mnt/pool/config"
        assert volume_1["mount_path"] == "/etc/config"
        assert volume_1["read_only"] is True

    @pytest.mark.asyncio
    async def test_storage_conversion_named_volumes(self, converter):
        """Test storage conversion with named volumes (IX volumes)."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx
    volumes:
      - app_data:/var/lib/app
      - cache_data:/var/cache
volumes:
  app_data:
  cache_data:
"""

        result = await converter.convert(compose_yaml, "test-app")

        storage = result["services"][0]["storage"]
        assert len(storage) == 2

        # Check named volumes become IX volumes
        volume_0 = storage["volume_0"]
        assert volume_0["type"] == "ix_volume"
        assert "ix_volume_config" in volume_0
        assert volume_0["ix_volume_config"]["dataset_name"] == "app_data"
        assert volume_0["ix_volume_config"]["acl_enable"] is False
        assert volume_0["mount_path"] == "/var/lib/app"

    @pytest.mark.asyncio
    async def test_environment_conversion_list_format(self, converter):
        """Test environment variable conversion from list format."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx
    environment:
      - NGINX_HOST=localhost
      - NGINX_PORT=80
      - DEBUG=true
"""

        result = await converter.convert(compose_yaml, "test-app")

        environment = result["services"][0]["environment"]
        assert environment["NGINX_HOST"] == "localhost"
        assert environment["NGINX_PORT"] == "80"
        assert environment["DEBUG"] == "true"

    @pytest.mark.asyncio
    async def test_environment_conversion_dict_format(self, converter):
        """Test environment variable conversion from dict format."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx
    environment:
      NGINX_HOST: localhost
      NGINX_PORT: 80
      DEBUG: true
"""

        result = await converter.convert(compose_yaml, "test-app")

        environment = result["services"][0]["environment"]
        assert environment["NGINX_HOST"] == "localhost"
        assert environment["NGINX_PORT"] == 80
        assert environment["DEBUG"] is True

    @pytest.mark.asyncio
    async def test_environment_conversion_no_env(self, converter):
        """Test environment conversion with no environment variables."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx
"""

        result = await converter.convert(compose_yaml, "test-app")

        environment = result["services"][0]["environment"]
        assert environment == {}

    @pytest.mark.asyncio
    async def test_invalid_yaml(self, converter):
        """Test conversion with invalid YAML."""
        invalid_yaml = "key: [unterminated"

        with pytest.raises(ValueError, match="Invalid YAML"):
            await converter.convert(invalid_yaml, "test-app")

    @pytest.mark.asyncio
    async def test_no_services(self, converter):
        """Test conversion with no services defined."""
        compose_yaml = """
version: '3'
networks:
  mynet:
"""

        with pytest.raises(ValueError, match="No services found"):
            await converter.convert(compose_yaml, "test-app")

    @pytest.mark.asyncio
    async def test_empty_services(self, converter):
        """Test conversion with empty services."""
        compose_yaml = """
version: '3'
services: {}
"""

        with pytest.raises(ValueError, match="No services found"):
            await converter.convert(compose_yaml, "test-app")

    @pytest.mark.asyncio
    async def test_multi_service_conversion(self, converter):
        """Test conversion handles all services in a compose file."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx:1.25
    ports:
      - "8080:80"
  db:
    image: postgres:13
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_PASSWORD=secret
"""

        result = await converter.convert(compose_yaml, "multi-app")

        assert len(result["services"]) == 2

        web = result["services"][0]
        assert web["name"] == "web"
        assert web["image"]["repository"] == "nginx"
        assert web["image"]["tag"] == "1.25"
        assert web["network"]["port_forwards"][0]["host_port"] == 8080

        db = result["services"][1]
        assert db["name"] == "db"
        assert db["image"]["repository"] == "postgres"
        assert db["image"]["tag"] == "13"
        assert db["network"]["port_forwards"][0]["host_port"] == 5432
        assert db["environment"]["POSTGRES_PASSWORD"] == "secret"

    @pytest.mark.asyncio
    async def test_three_service_conversion(self, converter):
        """Test conversion handles a typical 3-service stack."""
        compose_yaml = """
version: '3'
services:
  app:
    image: myapp:latest
    ports:
      - "3000:3000"
  db:
    image: postgres:15
    ports:
      - "5432:5432"
  redis:
    image: redis:7
    ports:
      - "6379:6379"
"""

        result = await converter.convert(compose_yaml, "full-stack")

        assert len(result["services"]) == 3
        names = [s["name"] for s in result["services"]]
        assert names == ["app", "db", "redis"]

    @pytest.mark.asyncio
    async def test_complex_compose_conversion(self, converter):
        """Test conversion of complex Docker Compose file."""
        compose_yaml = """
version: '3.8'
services:
  webapp:
    image: myapp:v2.1.0
    ports:
      - "3000:3000"
      - "3001:3001"
    environment:
      - NODE_ENV=production
      - DATABASE_URL=postgresql://user:pass@db:5432/myapp
      - REDIS_URL=redis://redis:6379
    volumes:
      - /mnt/pool/app/data:/app/data
      - /mnt/pool/app/logs:/app/logs:ro
      - app_uploads:/app/uploads
      - cache_data:/tmp/cache
    restart: unless-stopped

volumes:
  app_uploads:
  cache_data:

networks:
  app_network:
    driver: bridge
"""

        result = await converter.convert(compose_yaml, "complex-app")

        svc = result["services"][0]

        # Check image
        assert svc["image"]["repository"] == "myapp"
        assert svc["image"]["tag"] == "v2.1.0"

        # Check network with multiple ports
        port_forwards = svc["network"]["port_forwards"]
        assert len(port_forwards) == 2
        assert port_forwards[0]["host_port"] == 3000
        assert port_forwards[1]["host_port"] == 3001

        # Check environment variables
        env = svc["environment"]
        assert env["NODE_ENV"] == "production"
        assert "postgresql://" in env["DATABASE_URL"]
        assert env["REDIS_URL"] == "redis://redis:6379"

        # Check storage with mixed volume types
        storage = svc["storage"]
        assert len(storage) == 4

        # Host path volumes
        volume_0 = storage["volume_0"]
        assert volume_0["type"] == "host_path"
        assert volume_0["host_path"] == "/mnt/pool/app/data"

        # Named volumes become IX volumes
        found_ix_volume = False
        for vol_key, vol_config in storage.items():
            if vol_config["type"] == "ix_volume":
                found_ix_volume = True
                assert "ix_volume_config" in vol_config
                assert "dataset_name" in vol_config["ix_volume_config"]

        assert found_ix_volume, "Should have IX volumes for named volumes"

    @pytest.mark.asyncio
    async def test_yaml_size_limit(self, converter):
        """Test that oversized YAML input is rejected."""
        huge_yaml = "x" * (100 * 1024 + 1)

        with pytest.raises(ValueError, match="exceeds maximum size"):
            await converter.convert(huge_yaml, "test-app")

    @pytest.mark.asyncio
    async def test_path_traversal_normalized(self, converter):
        """Test that path traversal attempts are normalized."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx
    volumes:
      - /mnt/pool/../etc/passwd:/etc/passwd
"""

        result = await converter.convert(compose_yaml, "test-app")
        storage = result["services"][0]["storage"]
        volume = storage["volume_0"]
        # os.path.normpath resolves /mnt/pool/../etc to /mnt/etc
        # which does NOT start with /mnt/ followed by a pool name,
        # but does start with /mnt/ so it's treated as host_path
        # The normpath prevents the actual traversal
        assert ".." not in volume["host_path"]
