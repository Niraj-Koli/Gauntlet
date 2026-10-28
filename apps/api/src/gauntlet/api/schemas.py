"""Response and request bodies for /api/v1. Money is JSON numbers (dollars), times are
ISO 8601 UTC. The frontend's TypeScript types are generated from these via OpenAPI."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RunBrief(Out):
    id: int
    kind: Literal["trade", "rebalance"]
    status: Literal["running", "succeeded", "failed"]
    started_at: datetime
    finished_at: datetime | None
    summary: str | None
    outlook: str | None
    confidence: float | None
    error: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None


class TraderSummary(Out):
    id: int
    slug: str
    name: str
    tagline: str
    model: str
    model_label: str
    status: Literal["active", "paused"]
    cash: float
    holdings_value: float
    total_value: float
    starting_cash: float
    pnl: float
    return_pct: float
    change_24h: float | None
    positions: int
    sparkline: list[float] = Field(description="Recent portfolio values, oldest first")
    last_run: RunBrief | None
    running: bool


class PositionOut(Out):
    symbol: str
    quantity: int
    avg_cost: float
    price: float
    market_value: float
    unrealized_pnl: float
    weight_pct: float


class Stats(Out):
    return_pct: float
    volatility_pct: float | None
    sharpe: float | None
    max_drawdown_pct: float
    win_rate: float | None
    sells: int
    trades: int
    runs: int
    failed_runs: int
    total_cost_usd: float
    cost_per_run_usd: float | None
    input_tokens: int
    output_tokens: int


class TraderDetail(TraderSummary):
    strategy: str
    realized_pnl: float
    unrealized_pnl: float
    holdings: list[PositionOut]
    guardrails: dict[str, Any] = Field(description="The limits in force, defaults included")
    guardrail_overrides: dict[str, Any]
    stats: Stats


class TradeOut(Out):
    id: int
    run_id: int | None
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    price: float
    market_price: float
    realized_pnl: float | None
    rationale: str
    created_at: datetime


class PointOut(Out):
    t: datetime
    value: float


class SeriesOut(Out):
    portfolio: list[PointOut]
    benchmark: list[PointOut]
    benchmark_symbol: str


class EventOut(Out):
    id: int
    run_id: int | None
    created_at: datetime
    kind: str
    message: str
    span_id: str | None
    parent_id: str | None


class ActivityOut(Out):
    id: int
    created_at: datetime
    kind: str
    message: str
    run_id: int | None
    trader_slug: str
    trader_name: str


class RunDetail(RunBrief):
    trader_slug: str
    model: str
    trades: list[TradeOut]
    events: list[EventOut]


class StrategyOut(Out):
    id: int
    run_id: int | None
    strategy: str
    source: str
    created_at: datetime


class FloorOut(Out):
    market_source: str
    market_open: bool
    demo_mode: bool
    paused: bool
    scheduler_alive: bool
    last_cycle_at: datetime | None
    cycle_minutes: int


class ArenaRow(Out):
    model: str
    model_label: str
    traders: list[str]
    return_pct: float
    pnl: float
    sharpe: float | None
    max_drawdown_pct: float
    win_rate: float | None
    runs: int
    total_cost_usd: float
    cost_per_run_usd: float | None
    pnl_per_dollar: float | None = Field(description="Profit per dollar of model spend")


class ModelOut(Out):
    id: str
    label: str
    configured: bool = Field(description="Whether the API key this model needs is set")


class CommandOut(Out):
    id: int
    kind: str
    status: str
    created_at: datetime
    processed_at: datetime | None
    error: str | None


class MeOut(Out):
    admin: bool
    email: str | None
    method: Literal["supabase", "token", "none"]
    auth_configured: bool


# --- requests ---------------------------------------------------------------------------


class TraderCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$", description="Lowercase id used in URLs")
    name: str = Field(min_length=1, max_length=64)
    tagline: str = Field(default="Trader", max_length=64)
    model: str = Field(min_length=3, max_length=128)
    strategy: str = Field(min_length=1, max_length=20_000)
    starting_cash: float | None = Field(default=None, gt=0, le=1_000_000_000)
    guardrails: dict[str, Any] | None = None


class TraderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    tagline: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, min_length=3, max_length=128)
    status: Literal["active", "paused"] | None = None
    strategy: str | None = Field(default=None, min_length=1, max_length=20_000)
    guardrails: dict[str, Any] | None = Field(
        default=None, description="Replaces the overrides; {} restores the defaults"
    )
