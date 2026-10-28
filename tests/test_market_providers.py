"""Market data providers: simulator, Massive (with a fake client), caching and hours."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from gauntlet.market import (
    InvalidSymbol,
    PriceUnavailable,
    SimulatorProvider,
    create_market_provider,
    normalize_symbol,
    simulated_price,
)
from gauntlet.market.base import TTLCache
from gauntlet.market.calendar import nyse_is_open
from gauntlet.market.massive import MassiveProvider


class FakeMassive:
    """Mimics a Massive plan tier: methods before `tier` are rejected."""

    def __init__(self, tier: int = 0, price: float = 123.45):
        self.tier = tier
        self.price = price
        self.calls: list[str] = []
        self.status: str | Exception = "open"

    def _check(self, name: str, tier: int):
        self.calls.append(name)
        if tier < self.tier:
            raise PermissionError(f"{name} not in plan")

    def get_last_trade(self, symbol):
        self._check("last_trade", 0)
        return SimpleNamespace(price=self.price)

    def get_snapshot_ticker(self, market, symbol):
        self._check("snapshot", 1)
        return SimpleNamespace(min=SimpleNamespace(close=self.price), prev_day=SimpleNamespace(close=1.0))

    def get_previous_close_agg(self, symbol):
        self._check("previous_close", 2)
        return [SimpleNamespace(close=self.price)]

    def get_market_status(self):
        if isinstance(self.status, Exception):
            raise self.status
        return SimpleNamespace(market=self.status)


def test_symbols_are_upper_cased_and_validated():
    assert normalize_symbol(" brk.b ") == "BRK.B"
    for bad in ["", "1ABC", "TOOLONGSYMBOL", "A B", None]:
        with pytest.raises(InvalidSymbol):
            normalize_symbol(bad)  # pyright: ignore[reportArgumentType]


async def test_simulator_provider_matches_the_simulator():
    provider = SimulatorProvider()
    price = await provider.get_price("AAPL")
    assert isinstance(price, Decimal)
    assert abs(float(price) - simulated_price("AAPL")) < 5  # same function, a moment apart
    assert await provider.is_market_open()


def test_provider_choice_follows_the_massive_key(settings):
    assert create_market_provider(settings).name == "simulator"
    with_key = settings.model_copy(update={"massive_api_key": SecretStr("key")})
    assert create_market_provider(with_key).name == "massive"


async def test_massive_falls_back_through_plan_tiers_and_remembers_the_working_one():
    client = FakeMassive(tier=2)
    provider = MassiveProvider("key", price_cache_seconds=0, client=client)
    assert await provider.get_price("AAPL") == Decimal("123.45")
    assert client.calls == ["last_trade", "snapshot", "previous_close"]
    client.calls.clear()
    await provider.get_price("MSFT")
    assert client.calls == ["previous_close"]


async def test_massive_prices_are_cached():
    client = FakeMassive()
    provider = MassiveProvider("key", price_cache_seconds=60, client=client)
    await provider.get_price("AAPL")
    await provider.get_price("AAPL")
    assert client.calls == ["last_trade"]


async def test_massive_failure_raises_instead_of_inventing_a_price():
    """Phase 0 behaviour fell back to a simulated price, so agents traded on fake data."""
    client = FakeMassive(tier=3)
    provider = MassiveProvider("key", client=client)
    with pytest.raises(PriceUnavailable):
        await provider.get_price("AAPL")


async def test_massive_market_status_and_calendar_fallback(monkeypatch):
    client = FakeMassive()
    client.status = "closed"
    assert not await MassiveProvider("key", client=client).is_market_open()

    client.status = ConnectionError("down")
    monkeypatch.setattr("gauntlet.market.massive.nyse_is_open", lambda: False)
    assert not await MassiveProvider("key", client=client).is_market_open()


def test_nyse_calendar():
    assert nyse_is_open(datetime(2026, 10, 21, 15, 0, tzinfo=UTC))  # Wednesday 11:00 ET
    assert not nyse_is_open(datetime(2026, 10, 21, 22, 0, tzinfo=UTC))  # after the close
    assert not nyse_is_open(datetime(2026, 10, 24, 15, 0, tzinfo=UTC))  # Saturday
    assert not nyse_is_open(datetime(2026, 12, 25, 15, 0, tzinfo=UTC))  # Christmas


def test_ttl_cache_expires_entries():
    now = [0.0]
    cache: TTLCache[str, int] = TTLCache(10, clock=lambda: now[0])
    cache.set("a", 1)
    assert cache.get("a") == 1
    now[0] = 10.5
    assert cache.get("a") is None


class FakeAggs(FakeMassive):
    def __init__(self, closes: dict[str, float] | Exception):
        super().__init__()
        self.closes = closes
        self.agg_calls = 0

    def get_aggs(self, symbol, multiplier, timespan, start, end):
        self.agg_calls += 1
        if isinstance(self.closes, Exception):
            raise self.closes
        return [
            SimpleNamespace(
                timestamp=datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000, close=c
            )
            for day, c in self.closes.items()
        ]


async def test_massive_history_uses_each_days_latest_close_and_caches_it():
    client = FakeAggs({"2026-03-02": 10.0, "2026-03-04": 12.5})
    provider = MassiveProvider("key", price_cache_seconds=60, client=client)
    times = [datetime(2026, 3, d, 15, tzinfo=UTC) for d in (1, 3, 5)]
    assert await provider.prices_at("SPY", times) == [None, Decimal("10.0"), Decimal("12.5")]
    assert await provider.prices_at("SPY", times) == [None, Decimal("10.0"), Decimal("12.5")]
    assert client.agg_calls == 1
    assert await provider.prices_at("SPY", []) == []


async def test_massive_history_failures_give_no_prices():
    provider = MassiveProvider("key", price_cache_seconds=60, client=FakeAggs(RuntimeError("plan")))
    assert await provider.prices_at("SPY", [datetime(2026, 3, 2, tzinfo=UTC)]) == [None]


def test_the_nyse_calendar_knows_sessions_weekends_and_its_limits():
    assert nyse_is_open(datetime(2026, 3, 4, 15, 0, tzinfo=UTC))  # a Wednesday, 10:00 in New York
    assert not nyse_is_open(datetime(2026, 3, 4, 22, 0, tzinfo=UTC))  # after the close
    assert not nyse_is_open(datetime(2026, 3, 7, 15, 0, tzinfo=UTC))  # Saturday
    assert not nyse_is_open(datetime(1900, 1, 2, 15, 0, tzinfo=UTC))  # before the calendar starts
