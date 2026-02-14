"""Tests for TrueNAS client implementations."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from truenas_mcp.truenas_client import (
    TrueNASClient,
    TrueNASConnectionError,
    TrueNASAuthenticationError,
    TrueNASAPIError,
)
from truenas_mcp.mock_client import MockTrueNASClient


class TestMockTrueNASClient:
    """Test mock TrueNAS client functionality."""

    @pytest.fixture
    async def mock_client(self):
        """Create mock client."""
        client = MockTrueNASClient()
        await client.connect()
        return client

    @pytest.mark.asyncio
    async def test_connection_lifecycle(self):
        """Test connection/disconnection lifecycle."""
        client = MockTrueNASClient()

        # Initially not connected
        assert not client.connected
        assert not client.authenticated

        # Connect
        await client.connect()
        assert client.connected
        assert client.authenticated

        # Disconnect
        await client.disconnect()
        assert not client.connected
        assert not client.authenticated

    @pytest.mark.asyncio
    async def test_test_connection(self, mock_client):
        """Test connection testing."""
        result = await mock_client.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_list_custom_apps_all(self, mock_client):
        """Test listing all Custom Apps."""
        apps = await mock_client.list_custom_apps("all")

        assert len(apps) == 3
        app_names = [app["name"] for app in apps]
        assert "nginx-demo" in app_names
        assert "plex-server" in app_names
        assert "home-assistant" in app_names

    @pytest.mark.asyncio
    async def test_list_custom_apps_running_filter(self, mock_client):
        """Test listing only running apps."""
        apps = await mock_client.list_custom_apps("running")

        running_apps = [app for app in apps if app["status"] == "running"]
        assert len(running_apps) == len(apps)  # All returned should be running

    @pytest.mark.asyncio
    async def test_get_app_status_existing(self, mock_client):
        """Test getting status of existing app."""
        status = await mock_client.get_app_status("nginx-demo")
        assert status == "running"

    @pytest.mark.asyncio
    async def test_get_app_status_nonexistent(self, mock_client):
        """Test getting status of nonexistent app raises exception."""
        with pytest.raises(Exception, match="not found"):
            await mock_client.get_app_status("nonexistent-app")

    @pytest.mark.asyncio
    async def test_start_app_existing(self, mock_client):
        """Test starting existing app."""
        result = await mock_client.start_app("plex-server")
        assert result is True

        # Verify status changed
        status = await mock_client.get_app_status("plex-server")
        assert status == "running"

    @pytest.mark.asyncio
    async def test_start_app_nonexistent(self, mock_client):
        """Test starting nonexistent app."""
        result = await mock_client.start_app("nonexistent-app")
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_app_existing(self, mock_client):
        """Test stopping existing app."""
        result = await mock_client.stop_app("nginx-demo")
        assert result is True

        # Verify status changed
        status = await mock_client.get_app_status("nginx-demo")
        assert status == "stopped"

    @pytest.mark.asyncio
    async def test_deploy_app_success(self, mock_client):
        """Test successful app deployment."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx:latest
"""

        result = await mock_client.deploy_app("new-app", compose_yaml, auto_start=True)
        assert result is True

        # Verify app was added
        apps = await mock_client.list_custom_apps("all")
        app_names = [app["name"] for app in apps]
        assert "new-app" in app_names

    @pytest.mark.asyncio
    async def test_update_app_existing(self, mock_client):
        """Test updating existing app."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx:1.25
"""

        result = await mock_client.update_app("nginx-demo", compose_yaml, force_recreate=True)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_app_existing(self, mock_client):
        """Test deleting existing app."""
        result = await mock_client.delete_app("nginx-demo", delete_volumes=False)
        assert result is True

        # Verify app was removed
        apps = await mock_client.list_custom_apps("all")
        app_names = [app["name"] for app in apps]
        assert "nginx-demo" not in app_names

    @pytest.mark.asyncio
    async def test_validate_compose_valid(self, mock_client):
        """Test validating valid Docker Compose."""
        compose_yaml = """
version: '3'
services:
  web:
    image: nginx:latest
    ports:
      - "8080:80"
"""

        is_valid, issues = await mock_client.validate_compose(compose_yaml, check_security=True)
        assert is_valid is True
        assert isinstance(issues, list)

    @pytest.mark.asyncio
    async def test_validate_compose_invalid(self, mock_client):
        """Test validating invalid Docker Compose."""
        compose_yaml = "invalid yaml content"

        is_valid, issues = await mock_client.validate_compose(compose_yaml, check_security=True)
        assert is_valid is False
        assert len(issues) > 0

    @pytest.mark.asyncio
    async def test_get_app_logs_existing(self, mock_client):
        """Test getting logs from existing app."""
        logs = await mock_client.get_app_logs("nginx-demo", lines=50)

        assert isinstance(logs, str)
        assert len(logs) > 0
        assert "INFO" in logs or "WARN" in logs or "ERROR" in logs  # Mock logs contain these

    @pytest.mark.asyncio
    async def test_get_app_logs_nonexistent(self, mock_client):
        """Test getting logs from nonexistent app."""
        logs = await mock_client.get_app_logs("nonexistent-app", lines=50)
        assert logs == "App not found"


class TestTrueNASClient:
    """Test real TrueNAS client functionality."""

    @pytest.fixture
    def client_config(self):
        """Client configuration for testing (password auth)."""
        return {
            "host": "test.example.com",
            "username": "test-user",
            "password": "test-password",
            "port": 443,
            "protocol": "wss",
            "ssl_verify": False,
        }

    @pytest.fixture
    def api_key_config(self):
        """Client configuration for testing (API key auth)."""
        return {
            "host": "test.example.com",
            "username": "test-user",
            "api_key": "test-api-key",
            "port": 443,
            "protocol": "wss",
            "ssl_verify": False,
        }

    @pytest.fixture
    def truenas_client(self, client_config):
        """Create TrueNAS client for testing."""
        return TrueNASClient(**client_config)

    def test_client_initialization(self, truenas_client):
        """Test client initialization."""
        assert truenas_client.host == "test.example.com"
        assert truenas_client.password == "test-password"
        assert truenas_client.username == "test-user"
        assert truenas_client.port == 443
        assert truenas_client.protocol == "wss"
        assert truenas_client.ssl_verify is False
        assert truenas_client._client is None
        assert truenas_client.authenticated is False

    def test_client_requires_credential(self):
        """Test client requires either password or api_key."""
        with pytest.raises(ValueError, match="Either password or api_key"):
            TrueNASClient(host="test.example.com")

    def test_url_property(self, truenas_client):
        """Test URL property construction."""
        expected_url = "wss://test.example.com:443/api/current"
        assert truenas_client.url == expected_url

    @pytest.mark.asyncio
    @patch('truenas_mcp.truenas_client.TNClient')
    async def test_connect_success_password(self, mock_tn_client_class, truenas_client):
        """Test successful connection with password auth."""
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = True
        mock_tn_client_class.return_value = mock_tn_client

        await truenas_client.connect()

        mock_tn_client_class.assert_called_once_with(
            uri=truenas_client.url, verify_ssl=False
        )
        mock_tn_client.call.assert_called_once_with(
            "auth.login", "test-user", "test-password", None
        )
        assert truenas_client.authenticated is True

    @pytest.mark.asyncio
    @patch('truenas_mcp.truenas_client.TNClient')
    async def test_connect_password_failure(self, mock_tn_client_class, truenas_client):
        """Test connection with wrong password."""
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = False
        mock_tn_client_class.return_value = mock_tn_client

        with pytest.raises(TrueNASAuthenticationError, match="Authentication failed"):
            await truenas_client.connect()

    @pytest.mark.asyncio
    @patch('truenas_mcp.truenas_client.TNClient')
    async def test_connect_success_api_key(self, mock_tn_client_class, api_key_config):
        """Test successful connection with API key auth."""
        client = TrueNASClient(**api_key_config)
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = {"response_type": "SUCCESS"}
        mock_tn_client_class.return_value = mock_tn_client

        await client.connect()

        mock_tn_client.call.assert_called_once_with("auth.login_ex", {
            "mechanism": "API_KEY_PLAIN",
            "username": "test-user",
            "api_key": "test-api-key",
        })
        assert client.authenticated is True

    @pytest.mark.asyncio
    @patch('truenas_mcp.truenas_client.TNClient')
    async def test_connect_expired_key(self, mock_tn_client_class, api_key_config):
        """Test connection with expired/revoked key."""
        client = TrueNASClient(**api_key_config)
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = {"response_type": "EXPIRED"}
        mock_tn_client_class.return_value = mock_tn_client

        with pytest.raises(TrueNASAuthenticationError, match="Authentication failed"):
            await client.connect()

    @pytest.mark.asyncio
    @patch('truenas_mcp.truenas_client.TNClient')
    async def test_connect_connection_failure(self, mock_tn_client_class, truenas_client):
        """Test connection failure."""
        from truenas_api_client import ClientException
        mock_tn_client_class.side_effect = ClientException("Connection refused")

        with pytest.raises(TrueNASConnectionError, match="Connection failed"):
            await truenas_client.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, truenas_client):
        """Test disconnection."""
        mock_tn_client = MagicMock()
        truenas_client._client = mock_tn_client
        truenas_client.authenticated = True

        await truenas_client.disconnect()

        assert truenas_client._client is None
        assert truenas_client.authenticated is False
        mock_tn_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_not_connected(self, truenas_client):
        """Test API call without connection."""
        with pytest.raises(TrueNASConnectionError, match="Not connected"):
            await truenas_client._call("core.ping")

    @pytest.mark.asyncio
    async def test_call_success(self, truenas_client):
        """Test successful API call."""
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = "pong"
        truenas_client._client = mock_tn_client

        result = await truenas_client._call("core.ping")
        assert result == "pong"

    @pytest.mark.asyncio
    async def test_call_auth_error(self, truenas_client):
        """Test API call with auth error."""
        from truenas_api_client import ClientException
        mock_tn_client = MagicMock()
        mock_tn_client.call.side_effect = ClientException("[ENOTAUTHENTICATED] Not authenticated")
        truenas_client._client = mock_tn_client

        with pytest.raises(TrueNASAuthenticationError, match="Not authenticated"):
            await truenas_client._call("app.query")

    @pytest.mark.asyncio
    async def test_call_api_error(self, truenas_client):
        """Test API call with general API error."""
        from truenas_api_client import ClientException
        mock_tn_client = MagicMock()
        mock_tn_client.call.side_effect = ClientException("Some API error")
        truenas_client._client = mock_tn_client

        with pytest.raises(TrueNASAPIError, match="API call .* failed"):
            await truenas_client._call("app.query")

    @pytest.mark.asyncio
    async def test_test_connection_success(self, truenas_client):
        """Test successful connection test."""
        truenas_client.authenticated = True
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = "pong"
        truenas_client._client = mock_tn_client

        result = await truenas_client.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, truenas_client):
        """Test failed connection test."""
        truenas_client.authenticated = True
        mock_tn_client = MagicMock()
        mock_tn_client.call.side_effect = Exception("Connection error")
        truenas_client._client = mock_tn_client

        result = await truenas_client.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_list_custom_apps_success(self, truenas_client):
        """Test successful app listing."""
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = [
            {"name": "app1", "status": "running"},
            {"name": "app2", "status": "stopped"},
        ]
        truenas_client._client = mock_tn_client

        apps = await truenas_client.list_custom_apps("all")

        assert len(apps) == 2
        assert apps[0]["name"] == "app1"
        assert apps[1]["name"] == "app2"

    @pytest.mark.asyncio
    async def test_list_custom_apps_filtered(self, truenas_client):
        """Test filtered app listing."""
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = [
            {"name": "app1", "status": "running"},
            {"name": "app2", "status": "stopped"},
        ]
        truenas_client._client = mock_tn_client

        apps = await truenas_client.list_custom_apps("running")

        assert len(apps) == 1
        assert apps[0]["name"] == "app1"

    @pytest.mark.asyncio
    async def test_list_custom_apps_api_error(self, truenas_client):
        """Test app listing with API error."""
        from truenas_api_client import ClientException
        mock_tn_client = MagicMock()
        mock_tn_client.call.side_effect = ClientException("API error")
        truenas_client._client = mock_tn_client

        with pytest.raises(TrueNASAPIError):
            await truenas_client.list_custom_apps("all")

    @pytest.mark.asyncio
    async def test_get_app_status(self, truenas_client):
        """Test getting app status."""
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = {"name": "app1", "status": "running"}
        truenas_client._client = mock_tn_client

        status = await truenas_client.get_app_status("app1")
        assert status == "running"

    @pytest.mark.asyncio
    async def test_start_app_success(self, truenas_client):
        """Test starting an app."""
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = None
        truenas_client._client = mock_tn_client

        result = await truenas_client.start_app("app1")
        assert result is True

    @pytest.mark.asyncio
    async def test_start_app_failure(self, truenas_client):
        """Test starting an app that fails."""
        from truenas_api_client import ClientException
        mock_tn_client = MagicMock()
        mock_tn_client.call.side_effect = ClientException("App not found")
        truenas_client._client = mock_tn_client

        result = await truenas_client.start_app("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_app_success(self, truenas_client):
        """Test stopping an app."""
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = None
        truenas_client._client = mock_tn_client

        result = await truenas_client.stop_app("app1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_app_success(self, truenas_client):
        """Test deleting an app."""
        mock_tn_client = MagicMock()
        mock_tn_client.call.return_value = None
        truenas_client._client = mock_tn_client

        result = await truenas_client.delete_app("app1", delete_volumes=True)
        assert result is True
