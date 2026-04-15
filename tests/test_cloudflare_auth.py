"""Tests for Cloudflare Access authentication and rate limiting middleware."""

import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from truenas_mcp.cloudflare_auth import (
    CloudflareAccessMiddleware,
    RateLimitMiddleware,
    _fetch_cloudflare_jwks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_app(
    team_domain: str = "",
    audience: str = "",
    rate_limit_rpm: int = 60,
):
    """Build a minimal Starlette app with the middleware stack for testing."""

    async def echo(request: Request) -> JSONResponse:
        identity = getattr(request.state, "cf_access_identity", "anonymous")
        return JSONResponse({"identity": identity})

    async def health(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[
            Route("/mcp", echo, methods=["POST", "GET"]),
            Route("/health", health, methods=["GET"]),
        ],
    )

    app.add_middleware(
        CloudflareAccessMiddleware,
        team_domain=team_domain,
        audience=audience,
    )
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=rate_limit_rpm,
    )

    return app


# ---------------------------------------------------------------------------
# CloudflareAccessMiddleware tests
# ---------------------------------------------------------------------------

class TestCloudflareAccessMiddleware:
    """Test Cloudflare Access JWT validation middleware."""

    @pytest.mark.cloudflare
    def test_auth_disabled_when_no_config(self):
        """Requests pass through when CF_ACCESS_TEAM_DOMAIN is not set."""
        app = _build_app(team_domain="", audience="")
        client = TestClient(app)

        resp = client.post("/mcp")
        assert resp.status_code == 200
        assert resp.json()["identity"] == "anonymous"

    @pytest.mark.cloudflare
    def test_health_bypasses_auth(self):
        """Health endpoint skips authentication even when enabled."""
        app = _build_app(team_domain="test.cloudflareaccess.com", audience="test-aud")
        client = TestClient(app)

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.text == "ok"

    @pytest.mark.cloudflare
    def test_missing_token_returns_401(self):
        """Requests without Cf-Access-Jwt-Assertion get 401."""
        app = _build_app(team_domain="test.cloudflareaccess.com", audience="test-aud")
        client = TestClient(app)

        resp = client.post("/mcp")
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"] == "unauthorized"
        assert "Missing" in body["message"]

    @pytest.mark.cloudflare
    def test_invalid_token_returns_403(self):
        """Requests with a bad JWT get 403."""
        app = _build_app(team_domain="test.cloudflareaccess.com", audience="test-aud")
        client = TestClient(app)

        # Patch the JWKS fetch to return dummy keys so decode fails on signature
        with patch(
            "truenas_mcp.cloudflare_auth._fetch_cloudflare_jwks",
            new_callable=AsyncMock,
            return_value={"keys": []},
        ):
            resp = client.post(
                "/mcp",
                headers={"Cf-Access-Jwt-Assertion": "invalid.jwt.token"},
            )

        assert resp.status_code == 403
        body = resp.json()
        assert body["error"] == "forbidden"

    @pytest.mark.cloudflare
    def test_valid_token_passes_through(self):
        """Requests with a valid (mocked) JWT proceed to the handler."""
        app = _build_app(team_domain="test.cloudflareaccess.com", audience="test-aud")
        client = TestClient(app)

        mock_claims = {
            "email": "user@example.com",
            "sub": "user-id-123",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "iss": "https://test.cloudflareaccess.com",
            "aud": "test-aud",
        }

        with patch(
            "truenas_mcp.cloudflare_auth._fetch_cloudflare_jwks",
            new_callable=AsyncMock,
            return_value={"keys": [{"kid": "test-key"}]},
        ), patch(
            "truenas_mcp.cloudflare_auth._decode_cf_access_token",
            return_value=mock_claims,
        ):
            resp = client.post(
                "/mcp",
                headers={"Cf-Access-Jwt-Assertion": "valid.jwt.token"},
            )

        assert resp.status_code == 200
        assert resp.json()["identity"] == "user@example.com"


# ---------------------------------------------------------------------------
# RateLimitMiddleware tests
# ---------------------------------------------------------------------------

class TestRateLimitMiddleware:
    """Test rate limiting middleware."""

    @pytest.mark.cloudflare
    def test_requests_within_limit_pass(self):
        """Requests under the rate limit succeed."""
        app = _build_app(rate_limit_rpm=10)
        client = TestClient(app)

        for _ in range(10):
            resp = client.post("/mcp")
            assert resp.status_code == 200

    @pytest.mark.cloudflare
    def test_requests_over_limit_get_429(self):
        """Requests exceeding the rate limit get 429."""
        app = _build_app(rate_limit_rpm=3)
        client = TestClient(app)

        # First 3 should pass
        for _ in range(3):
            resp = client.post("/mcp")
            assert resp.status_code == 200

        # 4th should be rate limited
        resp = client.post("/mcp")
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"] == "rate_limited"
        assert "Retry-After" in resp.headers

    @pytest.mark.cloudflare
    def test_rate_limit_resets_after_window(self):
        """Rate limit window expires and allows new requests."""
        app = _build_app(rate_limit_rpm=2)
        client = TestClient(app)

        # Exhaust limit
        for _ in range(2):
            resp = client.post("/mcp")
            assert resp.status_code == 200

        # Should be blocked
        resp = client.post("/mcp")
        assert resp.status_code == 429

        # Manually expire the window by patching time
        with patch("truenas_mcp.cloudflare_auth.time") as mock_time:
            mock_time.time.return_value = time.time() + 61  # 61 seconds later
            resp = client.post("/mcp")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# JWKS fetching tests
# ---------------------------------------------------------------------------

class TestJWKSFetching:
    """Test Cloudflare Access public key fetching."""

    @pytest.mark.cloudflare
    @pytest.mark.asyncio
    async def test_jwks_fetch_and_cache(self):
        """JWKS are fetched from Cloudflare and cached."""
        import truenas_mcp.cloudflare_auth as auth_module

        mock_jwks = {"keys": [{"kid": "key1", "kty": "RSA"}]}

        # Clear cache first
        auth_module._jwks_cache = {}
        auth_module._jwks_cache_expiry = 0.0

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        with patch.object(
            auth_module.httpx, "AsyncClient"
        ) as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = mock_client

            result = await _fetch_cloudflare_jwks("test.cloudflareaccess.com")
            assert result == mock_jwks
            mock_client.get.assert_called_once_with(
                "https://test.cloudflareaccess.com/cdn-cgi/access/certs",
                timeout=10.0,
            )

    @pytest.mark.cloudflare
    @pytest.mark.asyncio
    async def test_jwks_uses_cache_within_ttl(self):
        """Cached JWKS are returned without refetching."""
        import truenas_mcp.cloudflare_auth as auth_module

        cached_keys = {"keys": [{"kid": "cached-key"}]}
        auth_module._jwks_cache = cached_keys
        auth_module._jwks_cache_expiry = time.time() + 300  # 5 minutes from now

        # httpx is a module-level import, so patch it properly
        with patch.object(auth_module.httpx, "AsyncClient") as mock_async_client:
            result = await _fetch_cloudflare_jwks("test.cloudflareaccess.com")
            assert result == cached_keys
            # httpx.AsyncClient should NOT have been called
            mock_async_client.assert_not_called()


# ---------------------------------------------------------------------------
# HTTP transport creation tests
# ---------------------------------------------------------------------------

class TestHTTPTransport:
    """Test HTTP transport app creation.

    These tests require mocking the truenas_api_client import since it
    may not be installed in the test environment.
    """

    @pytest.fixture(autouse=True)
    def mock_truenas_api_client(self):
        """Mock truenas_api_client so imports succeed without the real package."""
        import sys

        mock_module = MagicMock()
        modules_to_mock = {
            "truenas_api_client": mock_module,
        }
        with patch.dict(sys.modules, modules_to_mock):
            # Force reimport of the server module with mocked dependency
            for mod_name in list(sys.modules):
                if mod_name.startswith("truenas_mcp"):
                    del sys.modules[mod_name]
            yield
            # Clean up cached imports so other tests aren't affected
            for mod_name in list(sys.modules):
                if mod_name.startswith("truenas_mcp"):
                    del sys.modules[mod_name]

    @pytest.mark.cloudflare
    def test_create_http_app_returns_starlette(self):
        """create_http_app() returns a valid Starlette application."""
        env_vars = {
            "MOCK_TRUENAS": "true",
            "MCP_TRANSPORT": "http",
            "MCP_HTTP_PORT": "9999",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            from truenas_mcp.mcp_server import create_http_app

            app = create_http_app()
            assert app is not None

            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "healthy"
            assert body["transport"] == "http"

    @pytest.mark.cloudflare
    def test_create_http_app_with_cloudflare_config(self):
        """create_http_app() configures Cloudflare Access when env is set."""
        env_vars = {
            "MOCK_TRUENAS": "true",
            "MCP_TRANSPORT": "http",
            "CF_ACCESS_TEAM_DOMAIN": "myteam.cloudflareaccess.com",
            "CF_ACCESS_AUD": "my-aud-tag",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            from truenas_mcp.mcp_server import create_http_app

            app = create_http_app()
            client = TestClient(app)

            # Health endpoint bypasses auth
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["cloudflare_access"] == "enabled"

            # MCP endpoint requires auth when CF is configured
            resp = client.post("/mcp")
            assert resp.status_code == 401

    @pytest.mark.cloudflare
    def test_ready_endpoint_before_init(self):
        """Ready endpoint returns 503 before TrueNAS client initialization."""
        env_vars = {
            "MOCK_TRUENAS": "true",
            "MCP_TRANSPORT": "http",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            from truenas_mcp.mcp_server import create_http_app

            app = create_http_app()
            client = TestClient(app)

            resp = client.get("/ready")
            assert resp.status_code == 503
            assert resp.json()["status"] == "not_ready"
