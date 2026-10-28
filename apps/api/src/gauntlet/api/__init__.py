"""The Gauntlet HTTP API.

- /api/v1: the dashboard's data and the admin controls (see v1.py)
- /mcp/accounts/ and /mcp/market/: the MCP servers the traders connect to
- /healthz (the process is up) and /readyz (the database answers)

    uv run uvicorn gauntlet.api:app --port 8000
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.transport_security import TransportSecuritySettings
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text

from ..container import Container, build_container
from ..servers.accounts import build_accounts_server
from ..servers.auth import TraderTokenMiddleware
from ..servers.market import build_market_server
from . import v1
from .auth import AdminAuth


def create_app(container: Container | None = None) -> FastAPI:
    container = container or build_container()
    settings = container.settings

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=settings.mcp_allowed_hosts,
        allowed_origins=[f"http://{host}" for host in settings.mcp_allowed_hosts],
    )
    mcp_servers = {
        "accounts": build_accounts_server(container.accounts, security),
        "market": build_market_server(container.market, security),
    }

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await container.start()
        async with AsyncExitStack() as stack:
            for server in mcp_servers.values():
                await stack.enter_async_context(server.session_manager.run())
            yield
        await container.close()

    app = FastAPI(
        title="Gauntlet",
        version="1.0.0",
        description="Autonomous AI traders on a simulated trading floor.",
        lifespan=lifespan,
    )
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # pyright: ignore[reportArgumentType]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    secret = settings.gauntlet_secret_key.get_secret_value()
    for name, server in mcp_servers.items():
        app.mount(f"/mcp/{name}", TraderTokenMiddleware(server.streamable_http_app(), secret))

    app.include_router(v1.build_router(container, AdminAuth(settings), limiter))

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz(response: Response) -> dict:
        try:
            async with container.db.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "unavailable", "detail": type(e).__name__}
        return {"status": "ready"}

    return app


app = create_app()
