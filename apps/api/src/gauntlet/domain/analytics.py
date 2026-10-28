"""Performance statistics from a trader's portfolio snapshots, trades and runs.

Sharpe ratio and volatility use daily returns (each day's last portfolio value),
annualized over 252 trading days with a risk-free rate of zero. They need at least
MIN_DAILY_RETURNS days of history; before that they're None, because annualizing a few
minutes of noise produces numbers that look precise and mean nothing.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from ..db import PortfolioSnapshot, Run, Trade
from ..db.types import utcnow

TRADING_DAYS = 252
MIN_DAILY_RETURNS = 5


@dataclass(frozen=True)
class Performance:
    return_pct: float
    volatility_pct: float | None
    sharpe: float | None
    max_drawdown_pct: float
    win_rate: float | None
    """Share of sells that realized a profit."""
    sells: int
    trades: int
    runs: int
    failed_runs: int
    total_cost_usd: float
    priced_runs: int
    """Runs with a known cost (unpriced models leave it unknown)."""
    cost_per_run_usd: float | None
    input_tokens: int
    output_tokens: int


def _returns(values: list[float]) -> list[float]:
    return [b / a - 1 for a, b in zip(values, values[1:], strict=False) if a > 0]


def daily_values(snapshots: list[PortfolioSnapshot], current: float, today: date) -> list[float]:
    """Each UTC day's last portfolio value, with today's ending at the current value."""
    by_day: dict[date, float] = {}
    for s in snapshots:
        by_day[s.taken_at.date()] = float(s.total_value)
    by_day[today] = current
    return [by_day[day] for day in sorted(by_day)]


def max_drawdown(values: list[float]) -> float:
    """The largest fall from a peak, as a positive fraction."""
    peak, worst = -math.inf, 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def performance(
    snapshots: list[PortfolioSnapshot],
    current_value: Decimal,
    starting_cash: Decimal,
    trades: list[Trade],
    runs: list[Run],
    today: datetime | None = None,
) -> Performance:
    values = [float(s.total_value) for s in snapshots] + [float(current_value)]
    daily = _returns(daily_values(snapshots, float(current_value), (today or utcnow()).date()))
    volatility = sharpe = None
    if len(daily) >= MIN_DAILY_RETURNS:
        mean = sum(daily) / len(daily)
        std = math.sqrt(sum((r - mean) ** 2 for r in daily) / (len(daily) - 1))
        scale = math.sqrt(TRADING_DAYS)
        volatility = std * scale * 100
        sharpe = mean / std * scale if std > 0 else None
    sells = [t for t in trades if t.side == "sell" and t.realized_pnl is not None]
    finished = [r for r in runs if r.status != "running"]
    costs = [float(r.cost_usd) for r in finished if r.cost_usd is not None]
    return Performance(
        return_pct=float((current_value / starting_cash - 1) * 100) if starting_cash else 0.0,
        volatility_pct=volatility,
        sharpe=sharpe,
        max_drawdown_pct=max_drawdown(values) * 100,
        win_rate=sum(1 for t in sells if (t.realized_pnl or 0) > 0) / len(sells) if sells else None,
        sells=len(sells),
        trades=len(trades),
        runs=len(finished),
        failed_runs=sum(1 for r in finished if r.status == "failed"),
        total_cost_usd=sum(costs),
        priced_runs=len(costs),
        cost_per_run_usd=sum(costs) / len(costs) if costs else None,
        input_tokens=sum(r.input_tokens or 0 for r in finished),
        output_tokens=sum(r.output_tokens or 0 for r in finished),
    )


def value_at_or_before(snapshots: list[PortfolioSnapshot], moment: datetime) -> Decimal | None:
    """The last snapshot value at or before a moment, else the earliest one."""
    earlier = [s for s in snapshots if s.taken_at <= moment]
    if earlier:
        return earlier[-1].total_value
    return snapshots[0].total_value if snapshots else None


def change_since(
    snapshots: list[PortfolioSnapshot], current: Decimal, now: datetime, hours: int = 24
) -> Decimal | None:
    then = value_at_or_before(snapshots, now - timedelta(hours=hours))
    return None if then is None else current - then
