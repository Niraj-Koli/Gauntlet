"""Live prices from the Massive market data API."""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import anyio.to_thread
from massive import RESTClient

from .base import PriceUnavailable, TTLCache
from .calendar import nyse_is_open

logger = logging.getLogger(__name__)


def _last_trade(client: Any, symbol: str) -> float:
    return float(client.get_last_trade(symbol).price)


def _snapshot(client: Any, symbol: str) -> float:
    snapshot = client.get_snapshot_ticker("stocks", symbol)
    return float(snapshot.min.close or snapshot.prev_day.close)


def _previous_close(client: Any, symbol: str) -> float:
    return float(client.get_previous_close_agg(symbol)[0].close)


# Best price first, prior close last. Lower plan tiers reject the earlier calls, so we
# remember the first tier that works and start there next time.
PRICE_METHODS: list[Callable[[Any, str], float]] = [_last_trade, _snapshot, _previous_close]


class MassiveProvider:
    name = "massive"

    def __init__(
        self,
        api_key: str,
        price_cache_seconds: float = 60.0,
        status_cache_seconds: float = 300.0,
        client: Any = None,
    ):
        self.client: Any = client or RESTClient(api_key)
        self.plan_tier = 0
        self.prices: TTLCache[str, Decimal] = TTLCache(price_cache_seconds)
        self.status: TTLCache[str, bool] = TTLCache(status_cache_seconds)
        self.history: TTLCache[str, list[tuple[date, Decimal]]] = TTLCache(3600)

    async def get_price(self, symbol: str) -> Decimal:
        if (cached := self.prices.get(symbol)) is not None:
            return cached
        price = await anyio.to_thread.run_sync(self._fetch_price, symbol)
        self.prices.set(symbol, price)
        return price

    def _fetch_price(self, symbol: str) -> Decimal:
        for tier in range(self.plan_tier, len(PRICE_METHODS)):
            try:
                price = PRICE_METHODS[tier](self.client, symbol)
            except Exception as e:
                logger.debug("Massive %s failed for %s: %s", PRICE_METHODS[tier].__name__, symbol, e)
                continue
            if price > 0:
                self.plan_tier = tier
                return Decimal(str(price))
        # No silent fallback to simulated prices: trading on a fake price is worse than
        # not trading.
        raise PriceUnavailable(f"No market price available for {symbol}")

    async def prices_at(self, symbol: str, times: list[datetime]) -> list[Decimal | None]:
        """Each time's most recent daily close (Massive plans include daily history)."""
        if not times:
            return []
        start, end = min(times).date(), max(times).date()
        key = f"{symbol}:{start}:{end}"
        closes = self.history.get(key)
        if closes is None:
            try:
                closes = await anyio.to_thread.run_sync(self._daily_closes, symbol, start, end)
            except Exception as e:
                logger.warning("Massive history unavailable for %s: %s", symbol, e)
                return [None] * len(times)
            self.history.set(key, closes)
        result: list[Decimal | None] = []
        for when in times:
            earlier = [price for day, price in closes if day <= when.date()]
            result.append(earlier[-1] if earlier else None)
        return result

    def _daily_closes(self, symbol: str, start: date, end: date) -> list[tuple[date, Decimal]]:
        aggs = self.client.get_aggs(symbol, 1, "day", start - timedelta(days=7), end)
        return sorted(
            (datetime.fromtimestamp(a.timestamp / 1000, UTC).date(), Decimal(str(a.close))) for a in aggs
        )

    async def is_market_open(self) -> bool:
        if (cached := self.status.get("market")) is not None:
            return cached
        try:
            status = await anyio.to_thread.run_sync(self.client.get_market_status)
            is_open = getattr(status, "market", None) == "open"
        except Exception as e:
            logger.warning("Massive market status unavailable (%s); using the NYSE calendar", e)
            is_open = nyse_is_open()
        self.status.set("market", is_open)
        return is_open
