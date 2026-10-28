"""The market data interface the rest of Gauntlet depends on."""

import re
import time
from datetime import datetime
from decimal import Decimal
from typing import Protocol

SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class MarketDataError(Exception):
    """Base class for market data failures. Messages are safe to show to an agent."""


class InvalidSymbol(MarketDataError, ValueError):
    pass


class PriceUnavailable(MarketDataError):
    pass


def normalize_symbol(symbol: str) -> str:
    """Upper-case a ticker and check it looks like one, e.g. 'brk.b' -> 'BRK.B'."""
    cleaned = symbol.strip().upper() if isinstance(symbol, str) else ""
    if not SYMBOL_PATTERN.match(cleaned):
        raise InvalidSymbol(f"'{symbol}' is not a valid ticker symbol")
    return cleaned


class MarketDataProvider(Protocol):
    name: str
    """'simulator' or 'massive'."""

    async def get_price(self, symbol: str) -> Decimal:
        """Current price for a normalized symbol. Raises MarketDataError if there is none."""
        ...

    async def is_market_open(self) -> bool: ...

    async def prices_at(self, symbol: str, times: list[datetime]) -> list[Decimal | None]:
        """Historical prices for a symbol at each time, None where there's no data."""
        ...


class TTLCache[K, V]:
    """A small time-based cache; entries expire `ttl` seconds after they're stored."""

    def __init__(self, ttl: float, clock=time.monotonic):
        self.ttl = ttl
        self.clock = clock
        self._entries: dict[K, tuple[float, V]] = {}

    def get(self, key: K) -> V | None:
        entry = self._entries.get(key)
        if entry is None or entry[0] <= self.clock():
            return None
        return entry[1]

    def set(self, key: K, value: V) -> None:
        self._entries[key] = (self.clock() + self.ttl, value)
