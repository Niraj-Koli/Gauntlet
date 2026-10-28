"""ASGI middleware that admits MCP requests carrying a valid trader token."""

import json

from mcp.server.fastmcp import Context
from starlette.types import ASGIApp, Receive, Scope, Send

from ..security import InvalidToken, TraderIdentity, verify_token

IDENTITY_KEY = "gauntlet_identity"


class TraderTokenMiddleware:
    def __init__(self, app: ASGIApp, secret: str):
        self.app = app
        self.secret = secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        scheme, _, token = headers.get(b"authorization", b"").decode().partition(" ")
        try:
            if scheme.lower() != "bearer" or not token:
                raise InvalidToken("missing bearer token")
            identity = verify_token(self.secret, token)
        except InvalidToken as e:
            await _unauthorized(send, str(e))
            return
        scope.setdefault("state", {})[IDENTITY_KEY] = identity
        await self.app(scope, receive, send)


async def _unauthorized(send: Send, reason: str) -> None:
    body = json.dumps({"error": "unauthorized", "detail": reason}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")],
        }
    )
    await send({"type": "http.response.body", "body": body})


def identity_from(ctx: Context) -> TraderIdentity:
    """The trader behind the current MCP request, as verified by the middleware."""
    request = ctx.request_context.request
    identity = getattr(getattr(request, "state", None), IDENTITY_KEY, None)
    if not isinstance(identity, TraderIdentity):
        raise PermissionError("This MCP request isn't bound to a trader")
    return identity
