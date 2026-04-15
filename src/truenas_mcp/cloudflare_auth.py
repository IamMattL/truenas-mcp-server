"""Cloudflare Access authentication middleware for MCP server.

Validates Cloudflare Access JWT tokens on incoming requests,
ensuring only authenticated users can access the MCP server
when deployed behind Cloudflare AI Controls.
"""

import time
from typing import Any, Dict, List, Optional

import httpx
import jwt
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = structlog.get_logger(__name__)

# Cloudflare Access public key cache
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_expiry: float = 0.0
JWKS_CACHE_TTL = 300  # 5 minutes


async def _fetch_cloudflare_jwks(team_domain: str) -> Dict[str, Any]:
    """Fetch Cloudflare Access public keys (JWKS) for token verification.

    Args:
        team_domain: Cloudflare Access team domain (e.g., 'myteam.cloudflareaccess.com')

    Returns:
        JWKS key set as a dictionary.
    """
    global _jwks_cache, _jwks_cache_expiry

    now = time.time()
    if _jwks_cache and now < _jwks_cache_expiry:
        return _jwks_cache

    certs_url = f"https://{team_domain}/cdn-cgi/access/certs"
    logger.info("Fetching Cloudflare Access JWKS", url=certs_url)

    async with httpx.AsyncClient() as client:
        resp = await client.get(certs_url, timeout=10.0)
        resp.raise_for_status()
        jwks = resp.json()

    _jwks_cache = jwks
    _jwks_cache_expiry = now + JWKS_CACHE_TTL
    logger.info("Cloudflare Access JWKS cached", key_count=len(jwks.get("keys", [])))
    return jwks


def _decode_cf_access_token(
    token: str,
    jwks: Dict[str, Any],
    audience: str,
    team_domain: str,
) -> Dict[str, Any]:
    """Decode and verify a Cloudflare Access JWT token.

    Args:
        token: The JWT token from Cf-Access-Jwt-Assertion header.
        jwks: The JWKS key set from Cloudflare Access.
        audience: The Application Audience (AUD) tag from Cloudflare Access.
        team_domain: Cloudflare Access team domain for issuer validation.

    Returns:
        Decoded token claims.

    Raises:
        jwt.PyJWTError: If the token is invalid, expired, or fails verification.
    """
    # Get the signing key from the token header
    signing_key = jwt.PyJWK.from_dict(
        next(
            key
            for key in jwks["keys"]
            if key["kid"]
            == jwt.get_unverified_header(token)["kid"]
        )
    )

    decoded = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=f"https://{team_domain}",
        options={
            "require": ["exp", "iat", "iss", "aud", "sub"],
            "verify_exp": True,
            "verify_iss": True,
            "verify_aud": True,
        },
    )

    return decoded


class CloudflareAccessMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that validates Cloudflare Access JWT tokens.

    When your MCP server is placed behind Cloudflare Access (via Tunnel or
    MCP Server Portal), every request includes a signed JWT in the
    `Cf-Access-Jwt-Assertion` header. This middleware:

    1. Extracts the JWT from the request header
    2. Fetches/caches Cloudflare's public keys (JWKS)
    3. Validates the token signature, expiry, audience, and issuer
    4. Injects the authenticated user identity into request.state

    Configuration via environment variables:
        CF_ACCESS_TEAM_DOMAIN: Your Cloudflare Access team domain
            (e.g., 'myteam.cloudflareaccess.com')
        CF_ACCESS_AUD: The Application Audience (AUD) tag from your
            Cloudflare Access application configuration

    If neither is set, the middleware passes requests through without
    validation (for local development).
    """

    def __init__(
        self,
        app: Any,
        team_domain: Optional[str] = None,
        audience: Optional[str] = None,
        bypass_paths: Optional[List[str]] = None,
    ) -> None:
        super().__init__(app)
        self.team_domain = team_domain
        self.audience = audience
        self.bypass_paths = bypass_paths or ["/health", "/ready"]
        self.enabled = bool(team_domain and audience)

        if self.enabled:
            logger.info(
                "Cloudflare Access authentication enabled",
                team_domain=team_domain,
            )
        else:
            logger.warning(
                "Cloudflare Access authentication DISABLED - "
                "set CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD to enable"
            )

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """Validate Cloudflare Access token on each request."""
        # Skip auth for health/ready endpoints
        if request.url.path in self.bypass_paths:
            return await call_next(request)

        # If auth is not configured, pass through (local dev mode)
        if not self.enabled:
            return await call_next(request)

        # Extract the JWT from Cloudflare Access header
        token = request.headers.get("Cf-Access-Jwt-Assertion")
        if not token:
            logger.warning(
                "Missing Cf-Access-Jwt-Assertion header",
                path=request.url.path,
                client=request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Missing Cloudflare Access token",
                },
            )

        try:
            # Fetch public keys and verify token
            jwks = await _fetch_cloudflare_jwks(self.team_domain)
            claims = _decode_cf_access_token(
                token, jwks, self.audience, self.team_domain
            )

            # Inject identity into request state for downstream use
            request.state.cf_access_identity = claims.get("email", "unknown")
            request.state.cf_access_sub = claims.get("sub", "")
            request.state.cf_access_claims = claims

            logger.info(
                "Cloudflare Access token validated",
                identity=claims.get("email"),
                path=request.url.path,
            )

        except Exception as e:
            logger.warning(
                "Cloudflare Access token validation failed",
                error=str(e),
                path=request.url.path,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "forbidden",
                    "message": "Invalid or expired Cloudflare Access token",
                },
            )

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware.

    Provides basic request rate limiting per client IP. For production
    deployments behind Cloudflare, use Cloudflare's built-in rate limiting
    and AI Gateway rate controls instead - this serves as a defense-in-depth
    fallback.

    Configuration via environment variables:
        RATE_LIMIT_RPM: Maximum requests per minute per IP (default: 60)
    """

    def __init__(
        self,
        app: Any,
        requests_per_minute: int = 60,
    ) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._requests: Dict[str, List[float]] = {}

        logger.info(
            "Rate limiting enabled",
            requests_per_minute=requests_per_minute,
        )

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """Check rate limit before processing request."""
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - 60.0

        # Clean old entries and get current window
        if client_ip in self._requests:
            self._requests[client_ip] = [
                t for t in self._requests[client_ip] if t > window_start
            ]
        else:
            self._requests[client_ip] = []

        if len(self._requests[client_ip]) >= self.requests_per_minute:
            logger.warning(
                "Rate limit exceeded",
                client=client_ip,
                requests=len(self._requests[client_ip]),
                limit=self.requests_per_minute,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "message": f"Rate limit exceeded. Max {self.requests_per_minute} requests/minute.",
                },
                headers={"Retry-After": "60"},
            )

        self._requests[client_ip].append(now)
        return await call_next(request)
