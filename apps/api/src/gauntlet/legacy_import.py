"""Import an accounts.db from the original trading floor.

The old database kept each account as one JSON blob (balance, holdings, signed
transactions, value history) plus a logs table. Trades are replayed to rebuild average
costs and realized profit; the stored cash and holdings stay authoritative.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from .db import Database, Event, PortfolioSnapshot, Position, StrategyVersion, Trade, Trader
from .db.types import to_money
from .domain.accounts import TraderSeed
from .market import InvalidSymbol, normalize_symbol
from .settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class ImportReport:
    traders: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    trades: int = 0
    snapshots: int = 0
    events: int = 0
    warnings: list[str] = field(default_factory=list)


def _local_time(stamp: str) -> datetime:
    """Old account timestamps were naive local time."""
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").astimezone().astimezone(UTC)


def _utc_time(stamp: str) -> datetime:
    """Old log timestamps came from SQLite's datetime('now'), which is UTC."""
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _symbol(raw: str) -> str:
    try:
        return normalize_symbol(raw)
    except InvalidSymbol:
        return raw.strip().upper()[:16]


async def import_legacy(
    path: Path, db: Database, settings: Settings, seeds: list[TraderSeed], force: bool = False
) -> ImportReport:
    report = ImportReport()
    seeds_by_slug = {s.slug: s for s in seeds}
    spread = Decimal(settings.spread)
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as old:
        accounts = old.execute("SELECT name, account FROM accounts").fetchall()
        logs = old.execute("SELECT name, datetime, type, message FROM logs ORDER BY id").fetchall()

    for slug, blob in accounts:
        slug = slug.lower()
        account = json.loads(blob)
        async with db.transaction() as session:
            trader = await session.scalar(select(Trader).where(Trader.slug == slug))
            if trader is not None:
                has_history = await session.scalar(
                    select(func.count(Trade.id)).where(Trade.trader_id == trader.id)
                )
                if has_history and not force:
                    report.skipped.append(slug)
                    continue
                await session.delete(trader)  # cascades to its positions, trades and history
                await session.flush()
            seed = seeds_by_slug.get(slug)
            trader = Trader(
                slug=slug,
                name=seed.name if seed else slug.capitalize(),
                tagline=seed.tagline if seed else "Trader",
                model_name=seed.model_name if seed else "gpt-5.4-mini",
                strategy=account.get("strategy", "").strip(),
                cash=to_money(account["balance"]),
                starting_cash=to_money(settings.initial_balance),
            )
            session.add(trader)
            await session.flush()
            if trader.strategy:
                session.add(StrategyVersion(trader_id=trader.id, strategy=trader.strategy, source="import"))

            # Replay trades for average cost and realized profit.
            held: dict[str, tuple[int, Decimal]] = {}
            for t in account.get("transactions", []):
                symbol, quantity, price = _symbol(t["symbol"]), int(t["quantity"]), to_money(t["price"])
                if quantity == 0:
                    continue
                side = "buy" if quantity > 0 else "sell"
                quantity = abs(quantity)
                count, avg = held.get(symbol, (0, Decimal(0)))
                realized = None
                if side == "buy":
                    avg = to_money((avg * count + price * quantity) / (count + quantity))
                    count += quantity
                    market_price = to_money(price / (1 + spread))
                else:
                    realized = to_money((price - avg) * quantity)
                    count -= quantity
                    market_price = to_money(price / (1 - spread))
                held[symbol] = (count, avg)
                session.add(
                    Trade(
                        trader_id=trader.id,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        price=price,
                        market_price=market_price,
                        realized_pnl=realized,
                        rationale=t.get("rationale", ""),
                        created_at=_local_time(t["timestamp"]),
                    )
                )
                report.trades += 1

            for raw_symbol, quantity in account.get("holdings", {}).items():
                symbol = _symbol(raw_symbol)
                replayed, avg = held.get(symbol, (0, Decimal(0)))
                if replayed != quantity:
                    report.warnings.append(
                        f"{slug} {symbol}: holdings say {quantity}, trades replay to {replayed}; "
                        "using holdings"
                    )
                if quantity > 0:
                    session.add(Position(trader_id=trader.id, symbol=symbol, quantity=quantity, avg_cost=avg))

            for stamp, value in account.get("portfolio_value_time_series", []):
                total = to_money(value)
                session.add(
                    PortfolioSnapshot(
                        trader_id=trader.id,
                        taken_at=_local_time(stamp),
                        cash=trader.cash,
                        holdings_value=to_money(total - trader.cash),
                        total_value=total,
                    )
                )
                report.snapshots += 1

            for name, stamp, kind, message in logs:
                if name.lower() == slug:
                    session.add(
                        Event(trader_id=trader.id, created_at=_utc_time(stamp), kind=kind, message=message)
                    )
                    report.events += 1
            report.traders.append(slug)
    for warning in report.warnings:
        logger.warning(warning)
    return report
