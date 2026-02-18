# TrueNAS Scale MCP Server

A Model Context Protocol (MCP) server for managing TrueNAS Scale Custom Apps through Docker Compose deployments. This server enables AI assistants like Claude to deploy, manage, and monitor Docker-based applications on TrueNAS Scale systems using natural language.

## Overview

This MCP server wraps the official `truenas_api_client` (synchronous, websocket-based) with `asyncio.run_in_executor()` for non-blocking operation over MCP's stdio transport. It provides comprehensive Custom App management with automatic Docker Compose to TrueNAS format conversion.

## Features

- **20 MCP Tools** for complete app lifecycle, filesystem, ZFS, and system management
- **Docker Compose Conversion** to TrueNAS Custom App format with multi-service support
- **Password-based Authentication** (recommended) with API key fallback
- **Security Validation** preventing privileged containers and dangerous mounts
- **Lazy Client Initialization** - TrueNAS connection on first tool call, not server startup
- **Mock Development Mode** for testing without TrueNAS access
- **Comprehensive Test Suite** - 155 tests passing, 84% coverage
- **Thread-safe Async Wrapper** around synchronous TrueNAS API client

## Compatibility

- **MCP SDK**: v1.26.0
- **TrueNAS Scale**: 24.10+ (Electric Eel) and 25.10+ (Fangtooth)
- **Python**: 3.10+
- **Transport**: stdio with JSON-RPC 2.0

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Poetry for dependency management
- TrueNAS Scale 24.10+ with API access
- Service account credentials (username and password recommended)

### Installation

```bash
# Clone the repository
git clone https://github.com/IamMattL/truenas-mcp-server.git
cd truenas-mcp-server

# Install dependencies
poetry install

# Install pre-commit hooks (optional)
poetry run pre-commit install
```

### Service Account Setup

Create a dedicated service account on TrueNAS for MCP access:

1. Navigate to **Credentials > Local Users** in TrueNAS web UI
2. Create a new user:
   - **Username**: `mcp-service` (or your preferred name)
   - **Password**: Set a strong password
   - **Role**: Full Admin
   - **Disable 2FA**: Required for non-interactive authentication
3. Save the credentials for use in environment variables

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `TRUENAS_HOST` | TrueNAS hostname or IP address | `nas.pvnkn3t.lan` | Yes |
| `TRUENAS_PASSWORD` | Password for authentication (preferred) | None | One of password/api_key required |
| `TRUENAS_API_KEY` | API key for authentication (fallback) | None | One of password/api_key required |
| `TRUENAS_USERNAME` | Username for authentication | `mcp-service` | No |
| `TRUENAS_PORT` | WebSocket port | `443` | No |
| `TRUENAS_PROTOCOL` | WebSocket protocol (`ws` or `wss`) | `wss` | No |
| `TRUENAS_SSL_VERIFY` | Verify SSL certificates (`true`/`false`) | `true` | No |
| `DEBUG_MODE` | Enable debug logging (`true`/`false`) | `false` | No |
| `MOCK_TRUENAS` | Use mock client for development (`true`/`false`) | `false` | No |

### Testing the Server

```bash
# Test with mock TrueNAS (no real TrueNAS required)
MOCK_TRUENAS=true poetry run python -m truenas_mcp.mcp_server

# Test with real TrueNAS (requires valid credentials)
export TRUENAS_HOST="your-truenas-host"
export TRUENAS_USERNAME="mcp-service"
export TRUENAS_PASSWORD="your-password"
poetry run python -m truenas_mcp.mcp_server
```

## Claude Code Integration

The MCP server configuration must be added to `~/.claude.json` under the `mcpServers` key.

### Recommended: Using run_mcp.sh

The included `run_mcp.sh` script handles virtualenv resolution and module execution automatically via `poetry run`. This avoids hardcoding the Poetry virtualenv path (which contains a hash that changes if the venv is recreated).

Add to your `~/.claude.json`:

```json
{
  "mcpServers": {
    "truenas-scale": {
      "type": "stdio",
      "command": "/path/to/truenas-mcp-server/run_mcp.sh",
      "args": [],
      "env": {
        "TRUENAS_HOST": "your-truenas-host",
        "TRUENAS_USERNAME": "mcp-service",
        "TRUENAS_PASSWORD": "your-password",
        "TRUENAS_PORT": "443",
        "TRUENAS_PROTOCOL": "wss",
        "TRUENAS_SSL_VERIFY": "true"
      }
    }
  }
}
```

### Alternative: Direct Python Execution

If you prefer to bypass Poetry, you can point directly at the virtualenv Python binary. This requires both the virtualenv path and `PYTHONPATH` to be set manually:

```json
{
  "mcpServers": {
    "truenas-scale": {
      "type": "stdio",
      "command": "/path/to/poetry/virtualenv/bin/python",
      "args": ["-m", "truenas_mcp.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/truenas-mcp-server/src",
        "TRUENAS_HOST": "your-truenas-host",
        "TRUENAS_USERNAME": "mcp-service",
        "TRUENAS_PASSWORD": "your-password",
        "TRUENAS_PORT": "443",
        "TRUENAS_PROTOCOL": "wss",
        "TRUENAS_SSL_VERIFY": "true"
      }
    }
  }
}
```

Find your Poetry virtualenv path with:

```bash
poetry env info --path
```

## Authentication Methods

The server supports two authentication mechanisms with critical differences in behavior.

### Password Authentication (Recommended - PASSWORD_PLAIN)

Password authentication uses `auth.login(username, password, otp_token)` via WebSocket.

**Advantages:**
- **No transport security check** - works regardless of TrueNAS's secure_transport assessment
- Not subject to Network Exposure Protection (NEP) auto-revocation
- Reliable across different network configurations
- This is the recommended approach for external connections

**Configuration:**
```bash
export TRUENAS_USERNAME="mcp-service"
export TRUENAS_PASSWORD="your-password"
```

### API Key Authentication (Fallback - API_KEY_PLAIN)

API key authentication uses `auth.login_ex` with mechanism `API_KEY_PLAIN`.

**Critical Limitation - Network Exposure Protection (NEP):**

API keys are **subject to automatic revocation** when TrueNAS determines the connection is over "insecure transport". This is a security feature in TrueNAS that protects against credential exposure.

The `secure_transport` check in TrueNAS middleware evaluates:
- `self.ssl` flag (derived from nginx `X-Https` header)
- Unix socket connections (considered secure)
- HA connections between cluster nodes (considered secure)
- Loopback IP addresses (considered secure)

**Why API keys get revoked:**

On TrueNAS 25.10.1, the `get_tcp_ip_info()` function uses Linux `DiagSocket` (INET_DIAG) to verify socket UIDs and determine connection properties. When this diagnostic fails (common with external WebSocket connections), all return values are `None`:

```
ssl=None (falsy) → secure_transport=False → API key auto-revoked on first use
```

This means API keys often get auto-revoked immediately on first use from external hosts, even over encrypted WebSocket (wss://) connections, because the transport security assessment fails at the OS socket level.

**When to use API key authentication:**
- Only if password authentication is not possible
- Internal/localhost connections are more reliable
- Be prepared for potential revocation in production environments

**Configuration:**
```bash
export TRUENAS_USERNAME="mcp-service"
export TRUENAS_API_KEY="your-api-key"
```

### SCRAM Authentication Not Supported

Despite some documentation suggesting SCRAM-SHA512 support, TrueNAS 25.10.1's `AuthMech` enum only supports:
- `API_KEY_PLAIN`
- `PASSWORD_PLAIN`
- `TOKEN_PLAIN`
- `OTP_TOKEN`

SCRAM mechanisms are not available in the current TrueNAS API.

## Available MCP Tools

The server provides 20 MCP tools across five categories:

### Connection Management
- **`test_connection`** - Test TrueNAS API connectivity and authentication

### App Lifecycle
- **`list_custom_apps`** - List all apps with optional status filter (running/stopped/error/all)
- **`get_custom_app_status`** - Get status for a specific app
- **`get_custom_app_config`** - Get full app configuration (containers, images, ports, volumes, metadata)
- **`start_custom_app`** - Start a stopped app
- **`stop_custom_app`** - Stop a running app

### Deployment and Updates
- **`deploy_custom_app`** - Deploy a new Custom App from Docker Compose YAML
- **`update_custom_app`** - Update an app with new Docker Compose YAML
- **`update_custom_app_config`** - Update specific config fields without full Compose YAML
- **`delete_custom_app`** - Remove an app, optionally including data volumes

### Validation and Monitoring
- **`validate_compose`** - Validate Docker Compose YAML for TrueNAS compatibility
- **`get_app_logs`** - Retrieve app logs with configurable line limit and service filter

### Filesystem
- **`list_directory`** - Browse filesystem contents on TrueNAS (restricted to /mnt/)

### ZFS Management
- **`list_datasets`** - List ZFS datasets with usage information
- **`list_snapshots`** - List ZFS snapshots with size information
- **`create_snapshot`** - Create a ZFS snapshot for backup or rollback
- **`delete_snapshot`** - Delete a ZFS snapshot

### System Information
- **`get_system_info`** - Get system info (hostname, version, uptime, CPU, RAM)
- **`get_storage_pools`** - Get storage pool health, capacity, and scrub status
- **`get_network_info`** - Get network interface information (IPs, link state, speed)

## Usage Examples

Once configured in Claude Code, you can use natural language commands:

```
# App management
"List all my TrueNAS apps and their status"
"Show the full config of the tdarr app"
"Stop the app named 'plex'"
"Start the app named 'nextcloud'"

# Deployment
"Deploy this docker-compose.yml as a Custom App named 'my-app'"
"Update the app 'web-server' with this new docker-compose.yml"
"Validate this docker-compose.yml for TrueNAS compatibility"

# Logs and monitoring
"Show me the last 50 lines of logs from 'nginx'"

# ZFS snapshots
"Create a snapshot of Store/Media called 'pre-upgrade'"
"List all snapshots for Store/Media"

# System info
"Show TrueNAS system info"
"How much storage is available on my pools?"
"Show network interface status"

# Filesystem
"List the contents of /mnt/Store/Media"
```

## Architecture

### High-Level Overview

```
┌─────────────────┐    MCP Protocol     ┌──────────────────┐    WebSocket API    ┌─────────────────┐
│   AI Assistant  │ ◄──────────────────► │ TrueNAS MCP      │ ◄──────────────────► │ TrueNAS Scale   │
│   (Claude)      │    JSON-RPC 2.0     │ Server           │   auth + app.* RPC  │ 24.10+ / 25.10+ │
└─────────────────┘    stdio transport  └──────────────────┘                     └─────────────────┘
```

### Core Components

- **MCP Protocol Handler** (`mcp_server.py`) - Manages stdio transport and JSON-RPC 2.0 communication
- **TrueNAS API Client** (`truenas_client.py`) - Async wrapper around synchronous `truenas_api_client.Client`
- **Tools Handler** (`mcp_tools.py`) - Implements 20 MCP tools with JSON schema validation
- **Docker Compose Converter** (`compose_converter.py`) - Multi-service Docker Compose to TrueNAS format
- **Mock Client** (`mock_client.py`) - In-memory TrueNAS simulator for development

### Key Architectural Decisions

**Lazy Client Initialization:**
The TrueNAS connection is established on first tool call, not at server startup. This means `list_tools` works without a TrueNAS connection, improving startup reliability and allowing tool discovery before authentication.

**Thread-safe Async Wrapper:**
The official `truenas_api_client.Client` is synchronous and websocket-based. This server wraps all blocking calls with `asyncio.run_in_executor()` to prevent blocking the MCP event loop. Client initialization uses `asyncio.Lock()` for thread safety.

**Static Tool Listing:**
Tool definitions use `MCPToolsHandler(None)` - completely decoupled from the TrueNAS connection. This allows tool discovery to succeed even if TrueNAS is unreachable.

**MCP SDK v1.26.0 Compliance:**
- `Server.run()` requires 3 arguments: `(read_stream, write_stream, initialization_options)`
- `call_tool` handler must return a list of `TextContent`, not a single object
- Use `server.create_initialization_options()` for proper initialization

## Docker Compose Conversion

The server automatically converts Docker Compose files to TrueNAS Custom App format with comprehensive multi-service support.

### Supported Features

- **Volume Mounts**
  - Named volumes → TrueNAS IX volumes (managed storage)
  - Bind mounts → Host path mounts (direct filesystem access)
  - Volume permissions and ownership preservation

- **Port Forwarding**
  - Container ports → Host ports with protocol specification
  - Port conflict validation

- **Environment Variables**
  - Direct passthrough from compose to TrueNAS
  - Support for complex string values

- **Network Configuration**
  - Bridge mode (default, isolated network)
  - Host mode (direct host networking)

- **Restart Policies**
  - always, unless-stopped, on-failure → TrueNAS restart policy
  - Automatic policy normalization

### Security Validations

The server enforces security constraints to prevent dangerous configurations:

- **Blocks privileged container mode** - Prevents `privileged: true`
- **Prevents dangerous system directory mounts** - Blocks `/`, `/etc`, `/boot`, `/sys`, `/proc`
- **Validates port conflicts** - Ensures no duplicate host port bindings
- **Enforces resource limits** - Requires CPU/memory limits for production deployments
- **Input sanitization** - Validates all user-provided strings and paths

## Development

### Running Tests

```bash
# Run all tests (155 tests)
poetry run pytest

# Run with coverage report (84% coverage)
poetry run pytest --cov=src/truenas_mcp --cov-report=html

# Run specific test categories
poetry run pytest -m unit          # Unit tests only
poetry run pytest -m integration   # Integration tests only

# Run specific test file
poetry run pytest tests/test_mcp_server.py
```

### Code Quality

```bash
# Format code with Black
poetry run black .

# Lint code with Ruff
poetry run ruff check . --fix

# Type checking with mypy
poetry run mypy .

# Run all pre-commit checks
poetry run pre-commit run --all-files
```

### Mock Development Mode

Develop and test without a TrueNAS system using the built-in mock client:

```bash
# Enable mock mode
export MOCK_TRUENAS=true

# Run the server
poetry run python -m truenas_mcp.mcp_server

# Or inline
MOCK_TRUENAS=true poetry run python -m truenas_mcp.mcp_server
```

The mock client simulates TrueNAS API behavior with in-memory state management, supporting all 20 tools.

## Troubleshooting

### API Key Keeps Getting Revoked

**Symptom:** API key authentication works once, then immediately gets revoked by TrueNAS.

**Cause:** This is TrueNAS Network Exposure Protection (NEP). TrueNAS auto-revokes API keys used over connections it considers "insecure transport". The `secure_transport` assessment can fail for external WebSocket connections even over encrypted wss://, causing immediate revocation.

**Solution:** Switch to password authentication (PASSWORD_PLAIN). Password auth is not subject to the same transport security checks and works reliably across all network configurations.

```bash
# Replace API key with password
export TRUENAS_PASSWORD="your-password"
# Remove or comment out TRUENAS_API_KEY
```

### Server Doesn't Start with MCP

**Symptom:** Server fails to start when configured in `~/.claude.json` with import errors or "RuntimeWarning: coroutine was never awaited".

**Cause:** Server must be run with `-m truenas_mcp.mcp_server` due to relative imports. Direct script execution (`python src/truenas_mcp/mcp_server.py`) fails in MCP context.

**Solution:** Use `run_mcp.sh` which handles this automatically:

```json
{
  "command": "/path/to/truenas-mcp-server/run_mcp.sh",
  "args": []
}
```

Or if using direct Python execution, ensure module mode with `PYTHONPATH`:

```json
{
  "command": "/path/to/python",
  "args": ["-m", "truenas_mcp.mcp_server"],
  "env": {
    "PYTHONPATH": "/path/to/truenas-mcp-server/src"
  }
}
```

### SSL Verification Fails

**Symptom:** Connection fails with SSL certificate verification errors.

**Cause:** TrueNAS is using a self-signed certificate or certificate not in system trust store.

**Solution:** Disable SSL verification for development (not recommended for production):

```bash
export TRUENAS_SSL_VERIFY=false
```

For production, use a valid certificate from Let's Encrypt or your organization's CA.

### Connection Refused

**Symptom:** Unable to connect to TrueNAS WebSocket API.

**Causes and Solutions:**
- **Wrong host/port**: Verify `TRUENAS_HOST` and `TRUENAS_PORT` (default 443 for wss://)
- **Protocol mismatch**: Ensure `TRUENAS_PROTOCOL` matches your TrueNAS setup (wss:// for HTTPS, ws:// for HTTP)
- **Firewall blocking**: Check network firewall rules allow WebSocket connections
- **TrueNAS API disabled**: Verify API access is enabled in TrueNAS settings

Test connectivity manually:
```bash
curl -k -H "Authorization: Bearer YOUR_API_KEY" \
  https://nas.pvnkn3t.lan/api/v2.0/system/info
```

### Authentication Failed

**Symptom:** "Authentication failed" or "Invalid credentials" errors.

**Solutions:**
- **Verify credentials**: Double-check `TRUENAS_USERNAME` and `TRUENAS_PASSWORD`
- **Check 2FA**: Ensure service account has 2FA disabled (required for non-interactive auth)
- **Verify permissions**: Ensure user has Full Admin role
- **Test credentials**: Log in to TrueNAS web UI with same credentials

### RuntimeWarning: Coroutine Was Never Awaited

**Symptom:** Warning messages about unawaited coroutines during server startup.

**Cause:** Re-exporting `TrueNASMCPServer` from `__init__.py` when using `-m` flag causes import order issues.

**Solution:** This has been fixed in the current codebase. Don't re-export the server class from `__init__.py`.

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository at [https://github.com/IamMattL/truenas-mcp-server](https://github.com/IamMattL/truenas-mcp-server)
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes with clear, descriptive commits
4. Run tests: `poetry run pytest` (ensure all 155 tests pass)
5. Run quality checks: `poetry run pre-commit run --all-files`
6. Commit your changes: `git commit -m 'Add amazing feature'`
7. Push to your branch: `git push origin feature/amazing-feature`
8. Open a Pull Request with a clear description of the changes

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Project Status

- **Status**: Production Ready
- **MCP Protocol**: 2.0 Compatible
- **TrueNAS Compatibility**: Electric Eel (24.10+) and Fangtooth (25.10+)
- **Test Coverage**: 84% (155 tests passing)
- **Active Maintenance**: Yes

## Support

For issues, questions, or feature requests, please open an issue on GitHub at:
[https://github.com/IamMattL/truenas-mcp-server/issues](https://github.com/IamMattL/truenas-mcp-server/issues)

## Acknowledgments

- Built on the official [truenas_api_client](https://github.com/truenas/api_client) Python library
- Uses [MCP SDK](https://github.com/modelcontextprotocol/python-sdk) for protocol implementation
- Docker Compose conversion inspired by TrueNAS Custom App format requirements
