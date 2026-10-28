"""Share prices and market hours, from Massive when MASSIVE_API_KEY is set or the
simulator otherwise."""

from ..settings import Settings
from .base import InvalidSymbol, MarketDataError, MarketDataProvider, PriceUnavailable, normalize_symbol
from .simulator import SimulatorProvider, simulated_price


def create_market_provider(settings: Settings) -> MarketDataProvider:
    if api_key := settings.secret("massive_api_key"):
        from .massive import MassiveProvider

        return MassiveProvider(
            api_key,
            price_cache_seconds=settings.price_cache_seconds,
            status_cache_seconds=settings.market_status_cache_seconds,
        )
    return SimulatorProvider()


__all__ = [
    "InvalidSymbol",
    "MarketDataError",
    "MarketDataProvider",
    "PriceUnavailable",
    "SimulatorProvider",
    "create_market_provider",
    "normalize_symbol",
    "simulated_price",
]
