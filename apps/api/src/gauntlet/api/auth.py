"""Who may use the admin endpoints.

Two ways in, both as `Authorization: Bearer <token>`:
- a Supabase Auth access token for a user in ADMIN_EMAILS, verified with the project's
  JWKS (or SUPABASE_JWT_SECRET on projects still using the legacy shared secret);
- ADMIN_API_TOKEN, a static token for scripts and local development.

With neither configured, admin endpoints are closed. Repeated failed sign-ins from one
address are refused for a while (ADMIN_AUTH_FAILURE_LIMIT), so tokens can't be guessed.
"""

import hmac
import logging
from dataclasses import dataclass
from functools import cached_property
from typing import Literal

import jwt
from fastapi import HTTPException, Request, status
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from ..settings import Settings

logger = logging.getLogger(__name__)

AUDIENCE = "authenticated"


@dataclass(frozen=True)
class Principal:
    email: str | None
    method: Literal["supabase", "token", "none"]
    admin: bool


class AdminAuth:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.admin_emails = {e.strip().lower() for e in settings.admin_emails if e.strip()}
        self.failure_limit = parse(settings.admin_auth_failure_limit)
        self.failures = MovingWindowRateLimiter(MemoryStorage())

    @property
    def configured(self) -> bool:
        return bool(self.settings.secret("admin_api_token") or (self.supabase_enabled and self.admin_emails))

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.settings.supabase_url or self.settings.secret("supabase_jwt_secret"))

    @cached_property
    def _jwks(self) -> jwt.PyJWKClient | None:
        if not self.settings.supabase_url:
            return None
        url = f"{self.settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=5)

    def _verify_supabase(self, token: str) -> dict:
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "HS256":
            secret = self.settings.secret("supabase_jwt_secret")
            if not secret:
                raise jwt.InvalidTokenError("HS256 tokens need SUPABASE_JWT_SECRET")
            return jwt.decode(token, secret, algorithms=["HS256"], audience=AUDIENCE)
        if self._jwks is None:
            raise jwt.InvalidTokenError("SUPABASE_URL isn't set, so signing keys can't be fetched")
        key = self._jwks.get_signing_key_from_jwt(token)
        return jwt.decode(token, key.key, algorithms=["ES256", "RS256"], audience=AUDIENCE)

    def identify(self, request: Request) -> Principal:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return Principal(email=None, method="none", admin=False)
        client = request.client.host if request.client else "unknown"
        if not self.failures.test(self.failure_limit, "admin-auth", client):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed sign-ins; try again in a few minutes"
            )
        static = self.settings.secret("admin_api_token")
        if static and hmac.compare_digest(token.encode(), static.encode()):
            return Principal(email=None, method="token", admin=True)
        try:
            if not self.supabase_enabled:
                raise jwt.InvalidTokenError("not the admin token, and Supabase sign-in isn't configured")
            claims = self._verify_supabase(token)
        except jwt.PyJWTError as e:
            self.failures.hit(self.failure_limit, "admin-auth", client)
            logger.info("Rejected an admin token from %s: %s", client, e)
            detail = "Invalid or expired sign-in" if self.supabase_enabled else "Invalid admin token"
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail) from e
        email = (claims.get("email") or "").lower() or None
        return Principal(email=email, method="supabase", admin=email in self.admin_emails)

    def require_admin(self, request: Request) -> Principal:
        if not self.configured:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Admin access isn't configured (set ADMIN_API_TOKEN or ADMIN_EMAILS)",
            )
        principal = self.identify(request)
        if principal.method == "none":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to use admin controls")
        if not principal.admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"{principal.email} isn't an admin")
        return principal
