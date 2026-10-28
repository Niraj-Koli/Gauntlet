"""Performance statistics behind the dashboard's numbers."""

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from gauntlet.db import PortfolioSnapshot, Run, Trade
from gauntlet.domain.analytics import change_since, max_drawdown, performance

D = Decimal
START = datetime(2026, 10, 1, 20, tzinfo=UTC)


def snaps(values, step=timedelta(days=1)) -> list[PortfolioSnapshot]:
    return [PortfolioSnapshot(taken_at=START + i * step, total_value=D(str(v))) for i, v in enumerate(values)]


def run(status="succeeded", cost=None, tokens=(0, 0)) -> Run:
    return Run(status=status, cost_usd=cost, input_tokens=tokens[0], output_tokens=tokens[1])


def sell(pnl) -> Trade:
    return Trade(side="sell", realized_pnl=D(str(pnl)))


def test_max_drawdown():
    assert max_drawdown([100, 120, 90, 130, 117]) == pytest.approx(0.25)
    assert max_drawdown([100, 101, 102]) == 0


def test_sharpe_uses_daily_returns_and_needs_five_of_them():
    values = [10000, 10100, 10050, 10200, 10150, 10300]
    today = START + timedelta(days=6)
    early = performance(snaps(values[:4]), D("10200"), D("10000"), [], [], today=START + timedelta(days=3))
    assert early.sharpe is None and early.volatility_pct is None

    stats = performance(snaps(values), D("10300"), D("10000"), [], [], today=today)
    closes = [*values, 10300]  # one value per day, then today's current value
    returns = [b / a - 1 for a, b in zip(closes, closes[1:], strict=False)]
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
    assert stats.sharpe == pytest.approx(mean / std * math.sqrt(252))
    assert stats.return_pct == pytest.approx(3.0)


def test_intraday_noise_doesnt_produce_a_sharpe():
    minutes = snaps([10000, 9990, 10010, 9995, 10005, 9990, 10000], step=timedelta(minutes=1))
    assert performance(minutes, D("10000"), D("10000"), [], [], today=START).sharpe is None


def test_trades_runs_and_costs():
    stats = performance(
        snaps([10000]),
        D("10000"),
        D("10000"),
        [sell(5), sell(-2), sell(3), Trade(side="buy", realized_pnl=None)],
        [run(cost=D("0.02"), tokens=(1000, 200)), run(cost=None), run("failed", D("0.01")), run("running")],
    )
    assert (stats.sells, stats.trades, stats.win_rate) == (3, 4, pytest.approx(2 / 3))
    assert (stats.runs, stats.failed_runs, stats.priced_runs) == (3, 1, 2)
    assert stats.total_cost_usd == pytest.approx(0.03)
    assert stats.cost_per_run_usd == pytest.approx(0.015)
    assert (stats.input_tokens, stats.output_tokens) == (1000, 200)


def test_demo_runs_cost_zero_rather_than_unknown():
    stats = performance(snaps([10000]), D("10000"), D("10000"), [], [run(cost=D("0")), run(cost=D("0"))])
    assert stats.cost_per_run_usd == 0 and stats.priced_runs == 2


def test_change_since():
    history = snaps([10000, 10100, 10300], step=timedelta(hours=12))
    now = START + timedelta(hours=30)
    # 24 hours before hour 30 is hour 6; the last snapshot by then is hour 0's 10,000.
    assert change_since(history, D("10400"), now) == D("400")
    assert change_since([], D("10400"), now) is None
