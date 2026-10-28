"""The Gauntlet schema. Alembic migrations in db/migrations are the source of truth for
the database; these models must match them."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .types import Money, UTCDateTime, utcnow

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# SQLite only auto-increments INTEGER PRIMARY KEY columns.
BigId = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Trader(Base):
    __tablename__ = "traders"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    tagline: Mapped[str] = mapped_column(String(64), default="Trader")
    model_name: Mapped[str] = mapped_column(String(128))
    strategy: Mapped[str] = mapped_column(Text, default="")
    cash: Mapped[Decimal] = mapped_column(Money)
    starting_cash: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(16), default="active")
    guardrails: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    """Overrides for the default trading limits; see domain.guardrails."""
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (CheckConstraint("status IN ('active', 'paused')", name="status"),)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[int] = mapped_column(Integer)
    avg_cost: Mapped[Decimal] = mapped_column(Money)
    """Average price paid per share, spread included."""

    __table_args__ = (
        UniqueConstraint("trader_id", "symbol", name="uq_positions_trader_symbol"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    """The agent's appraisal of its portfolio."""
    outlook: Mapped[str | None] = mapped_column(String(16))
    confidence: Mapped[float | None] = mapped_column(Float)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Money)

    __table_args__ = (
        CheckConstraint("kind IN ('trade', 'rebalance')", name="kind"),
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status"),
    )


class Trade(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id", ondelete="CASCADE"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Money)
    """Price paid or received per share, spread included."""
    market_price: Mapped[Decimal] = mapped_column(Money)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Money)
    """Profit against average cost, for sells."""
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint("side IN ('buy', 'sell')", name="side"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_transactions_trader_created", "trader_id", "created_at"),
        Index("ix_transactions_run_id", "run_id"),
    )

    @property
    def signed_quantity(self) -> int:
        return self.quantity if self.side == "buy" else -self.quantity


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    strategy: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))
    """Who set it: seed, reset, agent, admin or import."""
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id", ondelete="CASCADE"))
    taken_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    cash: Mapped[Decimal] = mapped_column(Money)
    holdings_value: Mapped[Decimal] = mapped_column(Money)
    total_value: Mapped[Decimal] = mapped_column(Money)

    __table_args__ = (Index("ix_portfolio_snapshots_trader_taken", "trader_id", "taken_at"),)


class Event(Base):
    """Activity log lines: agent traces and account actions. Ordered by id."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    trader_id: Mapped[int | None] = mapped_column(ForeignKey("traders.id", ondelete="CASCADE"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    span_id: Mapped[str | None] = mapped_column(String(64))
    parent_id: Mapped[str | None] = mapped_column(String(64))
    """The parent span, or the trace id for top-level spans, so runs render as a tree."""

    __table_args__ = (
        Index("ix_events_trader_id_id", "trader_id", "id"),
        Index("ix_events_run_id_id", "run_id", "id"),
    )


COMMAND_KINDS = ("run_now", "pause_trader", "resume_trader", "pause_floor", "resume_floor")


class Command(Base):
    """An instruction for the scheduler, written by the CLI or (Phase 3) the admin API."""

    __tablename__ = "commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    trader_id: Mapped[int | None] = mapped_column(ForeignKey("traders.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(f"kind IN {COMMAND_KINDS}", name="kind"),
        CheckConstraint("status IN ('pending', 'done', 'failed')", name="status"),
        Index("ix_commands_status_id", "status", "id"),
    )


class FloorState(Base):
    """One row: whether the floor is paused, and which scheduler process leads it."""

    __tablename__ = "floor_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    leader_id: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_cycle_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
