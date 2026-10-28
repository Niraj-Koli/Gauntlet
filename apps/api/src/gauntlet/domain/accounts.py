"""Trader accounts: cash, positions, trades, strategies, snapshots and the activity log.

Every change happens in one database transaction that first locks the trader's row
(SELECT ... FOR UPDATE on Postgres; BEGIN IMMEDIATE on SQLite), so concurrent trades for
one trader apply one at a time against fresh balances.
"""

import asyncio
import re
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import Database, Event, PortfolioSnapshot, Position, Run, StrategyVersion, Trade, Trader
from ..db.types import to_money, utcnow
from ..market import MarketDataProvider, normalize_symbol
from ..settings import Settings
from .errors import InsufficientFunds, InsufficientShares, InvalidOrder, UnknownTrader
from .guardrails import Guardrails

INTERRUPTED = "Interrupted: the trading floor stopped before the run finished"

RECENT_TRADES_IN_REPORT = 20
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
# Bounds on what agents and admins can store: text the agent writes is kept, but not unboundedly,
# and amounts must fit the database's Numeric(20, 6).
MAX_STRATEGY_CHARS = 20_000
MAX_RATIONALE_CHARS = 4_000
MAX_STARTING_CASH = Decimal("1000000000")


@dataclass(frozen=True)
class PositionView:
    symbol: str
    quantity: int
    avg_cost: Decimal
    price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal


@dataclass(frozen=True)
class PortfolioView:
    trader: Trader
    cash: Decimal
    positions: list[PositionView]
    holdings_value: Decimal
    total_value: Decimal
    pnl: Decimal
    """Total value against the cash the trader started with."""
    realized_pnl: Decimal
    unrealized_pnl: Decimal


@dataclass(frozen=True)
class TradeResult:
    trade: Trade
    portfolio: PortfolioView


@dataclass(frozen=True)
class TraderSeed:
    slug: str
    name: str
    tagline: str
    model_name: str
    strategy: str


def _money(value: Decimal) -> float:
    """Decimal to a float rounded to cents, for JSON shown to agents and the dashboard."""
    return float(round(value, 2))


class AccountService:
    def __init__(self, db: Database, market: MarketDataProvider, settings: Settings):
        self.db = db
        self.market = market
        self.initial_balance = to_money(settings.initial_balance)
        self.spread = Decimal(settings.spread)
        self.max_order_quantity = settings.max_order_quantity

    # --- traders --------------------------------------------------------------------

    async def list_traders(self, active_only: bool = False) -> list[Trader]:
        query = select(Trader).order_by(Trader.id)
        if active_only:
            query = query.where(Trader.status == "active")
        async with self.db.sessions() as session:
            return list(await session.scalars(query))

    async def get_trader(self, slug: str) -> Trader:
        async with self.db.sessions() as session:
            trader = await session.scalar(select(Trader).where(Trader.slug == slug.lower()))
        if trader is None:
            raise UnknownTrader(f"Unknown trader {slug}")
        return trader

    async def get_trader_by_id(self, trader_id: int) -> Trader:
        async with self.db.sessions() as session:
            trader = await session.get(Trader, trader_id)
        if trader is None:
            raise UnknownTrader(f"Unknown trader id {trader_id}")
        return trader

    async def ensure_traders(self, seeds: list[TraderSeed]) -> list[Trader]:
        """Create any seeded traders that don't exist yet; existing ones are left alone."""
        async with self.db.transaction() as session:
            existing = set(await session.scalars(select(Trader.slug)))
            for seed in seeds:
                if seed.slug not in existing:
                    trader = Trader(
                        slug=seed.slug,
                        name=seed.name,
                        tagline=seed.tagline,
                        model_name=seed.model_name,
                        strategy=seed.strategy,
                        cash=self.initial_balance,
                        starting_cash=self.initial_balance,
                    )
                    session.add(trader)
                    await session.flush()
                    session.add(StrategyVersion(trader_id=trader.id, strategy=seed.strategy, source="seed"))
        return await self.list_traders()

    async def create_trader(
        self,
        seed: TraderSeed,
        starting_cash: Decimal | None = None,
        guardrails: dict[str, Any] | None = None,
    ) -> Trader:
        if not SLUG_PATTERN.match(seed.slug):
            raise InvalidOrder("Names must start with a letter and use only letters, digits and dashes")
        cash = to_money(starting_cash if starting_cash is not None else self.initial_balance)
        if not 0 < cash <= MAX_STARTING_CASH:
            raise InvalidOrder(f"Starting cash must be positive and at most ${MAX_STARTING_CASH:,}")
        _check_strategy(seed.strategy)
        if guardrails:
            Guardrails.for_trader(guardrails)
        async with self.db.transaction() as session:
            if await session.scalar(select(Trader.id).where(Trader.slug == seed.slug)) is not None:
                raise InvalidOrder(f"There's already a trader called {seed.slug}")
            trader = Trader(
                slug=seed.slug,
                name=seed.name,
                tagline=seed.tagline,
                model_name=seed.model_name,
                strategy=seed.strategy,
                cash=cash,
                starting_cash=cash,
                guardrails=guardrails or None,
            )
            session.add(trader)
            await session.flush()
            session.add(StrategyVersion(trader_id=trader.id, strategy=seed.strategy, source="admin"))
            session.add(Event(trader_id=trader.id, kind="account", message="Trader created"))
        return trader

    async def delete_trader(self, trader_id: int) -> None:
        """Remove a trader and everything recorded about it."""
        async with self.db.transaction() as session:
            trader = await self._lock_trader(session, trader_id)
            await session.delete(trader)

    async def reset(self, seed: TraderSeed, starting_cash: Decimal | None = None) -> Trader:
        """Back to starting cash and the seed strategy and model, with no positions or
        trades. Runs and the activity log are kept as history."""
        async with self.db.transaction() as session:
            trader = await session.scalar(select(Trader).where(Trader.slug == seed.slug).with_for_update())
            if trader is None:
                raise UnknownTrader(f"Unknown trader {seed.slug}")
            for table in (Position, Trade, PortfolioSnapshot):
                await session.execute(delete(table).where(table.trader_id == trader.id))
            trader.cash = trader.starting_cash = to_money(starting_cash or self.initial_balance)
            trader.strategy = seed.strategy
            trader.model_name = seed.model_name
            trader.tagline = seed.tagline
            session.add(StrategyVersion(trader_id=trader.id, strategy=seed.strategy, source="reset"))
            session.add(Event(trader_id=trader.id, kind="account", message="Account reset"))
        return trader

    # --- trading ----------------------------------------------------------------------

    def _validate_quantity(self, quantity: Any) -> int:
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise InvalidOrder("Quantity must be a whole number of shares")
        if quantity <= 0:
            raise InvalidOrder("Quantity must be at least 1 share")
        if quantity > self.max_order_quantity:
            raise InvalidOrder(f"Quantity can't exceed {self.max_order_quantity:,} shares in one order")
        return quantity

    async def _lock_trader(self, session: AsyncSession, trader_id: int) -> Trader:
        trader = await session.scalar(select(Trader).where(Trader.id == trader_id).with_for_update())
        if trader is None:
            raise UnknownTrader(f"Unknown trader id {trader_id}")
        return trader

    async def buy(
        self, trader_id: int, symbol: str, quantity: int, rationale: str, run_id: int | None = None
    ) -> TradeResult:
        symbol = normalize_symbol(symbol)
        quantity = self._validate_quantity(quantity)
        rationale = rationale[:MAX_RATIONALE_CHARS]
        guardrails = await self._guardrails(trader_id)
        # Network calls happen before taking the lock, so a slow price API doesn't block
        # other trades: this order's price, and current prices for valuing the portfolio.
        market_price = await self.market.get_price(symbol)
        price = to_money(market_price * (1 + self.spread))
        cost = to_money(price * quantity)
        before = await self.portfolio(trader_id)
        prices = {p.symbol: p.price for p in before.positions} | {symbol: market_price}

        async with self.db.transaction() as session:
            trader = await self._lock_trader(session, trader_id)
            if cost > trader.cash:
                raise InsufficientFunds(
                    f"Insufficient funds: {quantity} {symbol} at ${price:,.2f} costs ${cost:,.2f}, "
                    f"but cash is ${trader.cash:,.2f}"
                )
            positions = await session.scalars(select(Position).where(Position.trader_id == trader_id))
            held = {p.symbol: p for p in positions}
            position = held.get(symbol)
            holdings_value = sum(p.quantity * prices.get(p.symbol, p.avg_cost) for p in held.values())
            guardrails.check_buy(
                symbol,
                cost,
                position_value_after=((position.quantity if position else 0) + quantity) * market_price,
                portfolio_value=trader.cash + holdings_value,
                held_symbols=set(held),
            )
            if position is None:
                session.add(Position(trader_id=trader_id, symbol=symbol, quantity=quantity, avg_cost=price))
            else:
                total_cost = position.avg_cost * position.quantity + cost
                position.quantity += quantity
                position.avg_cost = to_money(total_cost / position.quantity)
            trader.cash = to_money(trader.cash - cost)
            trade = Trade(
                trader_id=trader_id,
                run_id=run_id,
                symbol=symbol,
                side="buy",
                quantity=quantity,
                price=price,
                market_price=to_money(market_price),
                rationale=rationale,
            )
            session.add(trade)
            self._log(session, trader_id, f"Bought {quantity} of {symbol}", run_id)
        return TradeResult(trade, await self.portfolio(trader_id))

    async def sell(
        self, trader_id: int, symbol: str, quantity: int, rationale: str, run_id: int | None = None
    ) -> TradeResult:
        symbol = normalize_symbol(symbol)
        quantity = self._validate_quantity(quantity)
        rationale = rationale[:MAX_RATIONALE_CHARS]
        await self._guardrails(trader_id)  # only the market-hours limit applies to sells
        market_price = await self.market.get_price(symbol)
        price = to_money(market_price * (1 - self.spread))

        async with self.db.transaction() as session:
            trader = await self._lock_trader(session, trader_id)
            position = await self._position(session, trader_id, symbol)
            held = position.quantity if position else 0
            if position is None or held < quantity:
                raise InsufficientShares(f"Cannot sell {quantity} shares of {symbol}: only {held} held")
            realized = to_money((price - position.avg_cost) * quantity)
            if held == quantity:
                await session.delete(position)
            else:
                position.quantity -= quantity
            trader.cash = to_money(trader.cash + price * quantity)
            trade = Trade(
                trader_id=trader_id,
                run_id=run_id,
                symbol=symbol,
                side="sell",
                quantity=quantity,
                price=price,
                market_price=to_money(market_price),
                realized_pnl=realized,
                rationale=rationale,
            )
            session.add(trade)
            self._log(session, trader_id, f"Sold {quantity} of {symbol}", run_id)
        return TradeResult(trade, await self.portfolio(trader_id))

    async def change_strategy(
        self, trader_id: int, strategy: str, source: str = "agent", run_id: int | None = None
    ) -> Trader:
        strategy = strategy.strip()
        _check_strategy(strategy)
        async with self.db.transaction() as session:
            trader = await self._lock_trader(session, trader_id)
            trader.strategy = strategy
            session.add(StrategyVersion(trader_id=trader_id, strategy=strategy, source=source, run_id=run_id))
            self._log(session, trader_id, "Changed strategy", run_id)
        return trader

    async def _guardrails(self, trader_id: int) -> Guardrails:
        """The trader's limits, after checking the market-hours one."""
        guardrails = Guardrails.for_trader((await self.get_trader_by_id(trader_id)).guardrails)
        if guardrails.trading_hours_only:
            guardrails.check_market(await self.market.is_market_open())
        return guardrails

    async def _position(self, session: AsyncSession, trader_id: int, symbol: str) -> Position | None:
        return await session.scalar(
            select(Position).where(Position.trader_id == trader_id, Position.symbol == symbol)
        )

    # --- configuration ----------------------------------------------------------------

    async def update_trader(
        self,
        trader_id: int,
        *,
        model_name: str | None = None,
        status: str | None = None,
        guardrails: dict[str, Any] | None = None,
        name: str | None = None,
        tagline: str | None = None,
    ) -> Trader:
        """Change a trader's model, status ('active' or 'paused'), guardrail overrides or
        display names. (Strategies change through change_strategy, which versions them.)"""
        if status is not None and status not in ("active", "paused"):
            raise InvalidOrder(f"Unknown status {status!r}")
        if guardrails is not None:
            Guardrails.for_trader(guardrails)  # validate before saving
        async with self.db.transaction() as session:
            trader = await self._lock_trader(session, trader_id)
            if model_name is not None:
                trader.model_name = model_name
            if status is not None:
                trader.status = status
            if guardrails is not None:
                trader.guardrails = guardrails or None
            if name is not None and name.strip():
                trader.name = name.strip()
            if tagline is not None:
                trader.tagline = tagline.strip()
        return trader

    # --- valuation --------------------------------------------------------------------

    async def portfolio(self, trader_id: int) -> PortfolioView:
        """Cash and positions valued at current prices. Reading has no side effects."""
        async with self.db.sessions() as session:
            trader = await session.get(Trader, trader_id)
            if trader is None:
                raise UnknownTrader(f"Unknown trader id {trader_id}")
            positions = list(
                await session.scalars(
                    select(Position).where(Position.trader_id == trader_id).order_by(Position.symbol)
                )
            )
            # Summed here rather than in SQL, which would go through float on SQLite.
            realized_rows = list(
                await session.scalars(
                    select(Trade.realized_pnl).where(Trade.trader_id == trader_id, Trade.side == "sell")
                )
            )
        prices = await asyncio.gather(*(self.market.get_price(p.symbol) for p in positions))
        views = [
            PositionView(
                symbol=p.symbol,
                quantity=p.quantity,
                avg_cost=p.avg_cost,
                price=price,
                market_value=to_money(price * p.quantity),
                unrealized_pnl=to_money((price - p.avg_cost) * p.quantity),
            )
            for p, price in zip(positions, prices, strict=True)
        ]
        holdings_value = to_money(sum((v.market_value for v in views), Decimal(0)))
        total = to_money(trader.cash + holdings_value)
        return PortfolioView(
            trader=trader,
            cash=trader.cash,
            positions=views,
            holdings_value=holdings_value,
            total_value=total,
            pnl=to_money(total - trader.starting_cash),
            realized_pnl=to_money(sum((r for r in realized_rows if r is not None), Decimal(0))),
            unrealized_pnl=to_money(sum((v.unrealized_pnl for v in views), Decimal(0))),
        )

    async def report(self, trader_id: int) -> dict[str, Any]:
        """The account as the agent sees it in its prompt and after each trade."""
        portfolio = await self.portfolio(trader_id)
        recent = await self.trades(trader_id, limit=RECENT_TRADES_IN_REPORT)
        return {
            "name": portfolio.trader.name,
            "strategy": portfolio.trader.strategy,
            "cash": _money(portfolio.cash),
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_cost": _money(p.avg_cost),
                    "price": _money(p.price),
                    "market_value": _money(p.market_value),
                    "unrealized_pnl": _money(p.unrealized_pnl),
                }
                for p in portfolio.positions
            ],
            "holdings_value": _money(portfolio.holdings_value),
            "total_portfolio_value": _money(portfolio.total_value),
            "total_profit_loss": _money(portfolio.pnl),
            "realized_pnl": _money(portfolio.realized_pnl),
            "unrealized_pnl": _money(portfolio.unrealized_pnl),
            "limits": Guardrails.for_trader(portfolio.trader.guardrails).describe(),
            "recent_transactions": [
                {
                    "time": t.created_at.isoformat(timespec="seconds"),
                    "side": t.side,
                    "symbol": t.symbol,
                    "quantity": t.quantity,
                    "price": _money(t.price),
                    "rationale": t.rationale,
                }
                for t in reversed(recent)
            ],
        }

    async def record_snapshot(self, trader_id: int, taken_at: datetime | None = None) -> PortfolioSnapshot:
        portfolio = await self.portfolio(trader_id)
        snapshot = PortfolioSnapshot(
            trader_id=trader_id,
            taken_at=taken_at or utcnow(),
            cash=portfolio.cash,
            holdings_value=portfolio.holdings_value,
            total_value=portfolio.total_value,
        )
        async with self.db.transaction() as session:
            session.add(snapshot)
        return snapshot

    # --- history ----------------------------------------------------------------------

    async def trades(self, trader_id: int, limit: int = 500) -> list[Trade]:
        """Most recent trades first."""
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(Trade)
                    .where(Trade.trader_id == trader_id)
                    .order_by(Trade.created_at.desc(), Trade.id.desc())
                    .limit(limit)
                )
            )

    async def run_trades(self, run_id: int) -> list[Trade]:
        """A run's trades, in the order they were made."""
        async with self.db.sessions() as session:
            return list(await session.scalars(select(Trade).where(Trade.run_id == run_id).order_by(Trade.id)))

    async def snapshots(self, trader_id: int, limit: int = 2000) -> list[PortfolioSnapshot]:
        """The latest snapshots, oldest first."""
        async with self.db.sessions() as session:
            rows = await session.scalars(
                select(PortfolioSnapshot)
                .where(PortfolioSnapshot.trader_id == trader_id)
                .order_by(PortfolioSnapshot.taken_at.desc(), PortfolioSnapshot.id.desc())
                .limit(limit)
            )
            return list(reversed(list(rows)))

    async def strategy_history(self, trader_id: int) -> list[StrategyVersion]:
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(StrategyVersion)
                    .where(StrategyVersion.trader_id == trader_id)
                    .order_by(StrategyVersion.id)
                )
            )

    async def events(self, trader_id: int, last_n: int = 13) -> list[Event]:
        """The latest activity log lines, oldest first, in the order they were written."""
        async with self.db.sessions() as session:
            rows = await session.scalars(
                select(Event).where(Event.trader_id == trader_id).order_by(Event.id.desc()).limit(last_n)
            )
            return list(reversed(list(rows)))

    async def recent_events(self, kinds: list[str], limit: int = 40) -> list[Event]:
        """The latest events of these kinds across every trader, newest first."""
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(Event).where(Event.kind.in_(kinds)).order_by(Event.id.desc()).limit(limit)
                )
            )

    async def run_events(self, run_id: int, limit: int = 5000) -> list[Event]:
        """A run's activity in the order it was written: its trace and account actions."""
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(Event).where(Event.run_id == run_id).order_by(Event.id).limit(limit)
                )
            )

    async def log_events(self, events: list[Event]) -> None:
        async with self.db.transaction() as session:
            session.add_all(events)

    def _log(self, session: AsyncSession, trader_id: int, message: str, run_id: int | None) -> None:
        session.add(Event(trader_id=trader_id, run_id=run_id, kind="account", message=message))

    # --- runs -------------------------------------------------------------------------

    async def next_run_kind(self, trader_id: int) -> str:
        """Traders alternate between looking for new trades and rebalancing."""
        async with self.db.sessions() as session:
            last = await session.scalar(
                select(Run.kind)
                .where(Run.trader_id == trader_id, Run.status != "running")
                .order_by(Run.id.desc())
                .limit(1)
            )
        return "rebalance" if last == "trade" else "trade"

    async def start_run(self, trader_id: int, kind: str) -> Run:
        async with self.db.transaction() as session:
            run = Run(trader_id=trader_id, kind=kind, status="running")
            session.add(run)
        return run

    async def finish_run(
        self,
        run_id: int,
        *,
        error: str | None = None,
        summary: str | None = None,
        outlook: str | None = None,
        confidence: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: Decimal | None = None,
    ) -> None:
        async with self.db.transaction() as session:
            run = await session.get(Run, run_id)
            if run is None:
                return
            run.status = "failed" if error else "succeeded"
            run.error = error
            run.summary = summary
            run.outlook = outlook
            run.confidence = confidence
            run.input_tokens = input_tokens
            run.output_tokens = output_tokens
            run.cost_usd = cost_usd
            run.finished_at = utcnow()

    async def abandon_runs(self, keep: Collection[int] = ()) -> int:
        """Mark runs left "running" by a scheduler that stopped mid-run as failed.

        Call only while holding the leader lease, so no other scheduler owns them; keep
        lists traders whose runs this process is still running."""
        async with self.db.transaction() as session:
            runs = (
                await session.scalars(
                    select(Run).where(Run.status == "running", Run.trader_id.not_in(list(keep)))
                )
            ).all()
            for run in runs:
                run.status = "failed"
                run.error = INTERRUPTED
                run.finished_at = utcnow()
        return len(runs)

    async def run_has_trades(self, run_id: int) -> bool:
        async with self.db.sessions() as session:
            return bool(await session.scalar(select(func.count(Trade.id)).where(Trade.run_id == run_id)))

    async def get_run(self, run_id: int) -> Run | None:
        async with self.db.sessions() as session:
            return await session.get(Run, run_id)

    async def runs(self, trader_id: int, limit: int = 50) -> list[Run]:
        """Most recent runs first."""
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(Run).where(Run.trader_id == trader_id).order_by(Run.id.desc()).limit(limit)
                )
            )


def _check_strategy(strategy: str) -> None:
    if not strategy.strip():
        raise InvalidOrder("Strategy can't be empty")
    if len(strategy) > MAX_STRATEGY_CHARS:
        raise InvalidOrder(f"Strategies are limited to {MAX_STRATEGY_CHARS:,} characters")
