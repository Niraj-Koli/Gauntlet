"""Shared fixtures. Each test gets a fresh database and a fake market with fixed prices,
so the suite never touches data/ or calls the Massive API.

Tests run on SQLite. Set TEST_DATABASE_URL to a Postgres database (e.g. the local
Supabase stack) to run every database test against it as well; its tables are emptied
between tests, so don't point it at data you care about.
"""

import os
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy import text

from gauntlet.container import Container, build_container
from gauntlet.db import Database
from gauntlet.db.models import Base
from gauntlet.market import PriceUnavailable
from gauntlet.settings import Settings

POSTGRES_URL = os.getenv("TEST_DATABASE_URL")
BACKENDS = ["sqlite", *(["postgres"] if POSTGRES_URL else [])]


class FakeMarket:
    """AAPL, MSFT and SPY at fixed prices; any other symbol has no price."""

    name = "fake"

    def __init__(self) -> None:
        self.prices = {"AAPL": Decimal("100"), "MSFT": Decimal("250"), "SPY": Decimal("500")}
        self.open = True

    async def get_price(self, symbol: str) -> Decimal:
        if symbol not in self.prices:
            raise PriceUnavailable(f"No market price available for {symbol}")
        return self.prices[symbol]

    async def is_market_open(self) -> bool:
        return self.open

    async def prices_at(self, symbol: str, times: list) -> list[Decimal | None]:
        """History is flat: today's price at every time, if the symbol has one."""
        return [self.prices.get(symbol) for _ in times]


@pytest.fixture(params=BACKENDS)
def database_url(request, tmp_path) -> str:
    if request.param == "postgres":
        assert POSTGRES_URL
        return POSTGRES_URL
    return f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def settings(database_url, tmp_path) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        gauntlet_data_dir=tmp_path,
        database_url=database_url,
        massive_api_key=None,
        gauntlet_secret_key="test-secret",  # pyright: ignore[reportArgumentType]
    )


@pytest.fixture
def market() -> FakeMarket:
    return FakeMarket()


async def _empty_postgres(db: Database) -> None:
    await db.migrate()
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with db.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def container(settings, market) -> AsyncIterator[Container]:
    container = build_container(settings, market=market)
    if container.db.dialect == "postgresql":
        await _empty_postgres(container.db)
    await container.start()
    yield container
    await container.close()


@pytest.fixture
def accounts(container):
    return container.accounts
