"""Builds the shared services once per process."""

from dataclasses import dataclass

from .db import Database
from .domain import AccountService, FloorControl
from .market import MarketDataProvider, create_market_provider
from .personas import default_traders
from .settings import Settings, get_settings


@dataclass
class Container:
    settings: Settings
    db: Database
    market: MarketDataProvider
    accounts: AccountService
    floor: FloorControl

    async def start(self) -> None:
        """Migrate if configured, and make sure the starting traders exist."""
        if self.settings.auto_migrate:
            await self.db.migrate()
        await self.accounts.ensure_traders(default_traders(self.settings))
        await self.floor.ensure_state()

    async def close(self) -> None:
        await self.db.dispose()


def build_container(settings: Settings | None = None, market: MarketDataProvider | None = None) -> Container:
    settings = settings or get_settings()
    db = Database(settings.database_url)
    market = market or create_market_provider(settings)
    return Container(settings, db, market, AccountService(db, market, settings), FloorControl(db))
