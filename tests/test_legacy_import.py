"""Importing an accounts.db from the original trading floor."""

import json
import sqlite3
from decimal import Decimal

import pytest

from gauntlet.legacy_import import import_legacy
from gauntlet.personas import default_traders

D = Decimal


@pytest.fixture
def legacy_db(tmp_path):
    path = tmp_path / "accounts.db"
    account = {
        "name": "warren",
        "balance": 8_507.4,
        "strategy": "Old value strategy",
        "holdings": {"AAPL": 5, "msft": 2},
        "transactions": [
            {
                "symbol": "AAPL",
                "quantity": 10,
                "price": 100.2,
                "timestamp": "2026-03-02 10:00:00",
                "rationale": "a",
            },
            {
                "symbol": "AAPL",
                "quantity": -5,
                "price": 110.0,
                "timestamp": "2026-03-03 10:00:00",
                "rationale": "b",
            },
            {
                "symbol": "msft",
                "quantity": 2,
                "price": 250.5,
                "timestamp": "2026-03-04 10:00:00",
                "rationale": "c",
            },
        ],
        "portfolio_value_time_series": [["2026-03-02 10:00:00", 10000.0], ["2026-03-04 10:00:00", 10050.0]],
    }
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE accounts (name TEXT PRIMARY KEY, account TEXT)")
        conn.execute(
            "CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, datetime DATETIME, "
            "type TEXT, message TEXT)"
        )
        conn.execute("INSERT INTO accounts VALUES (?, ?)", ("warren", json.dumps(account)))
        conn.executemany(
            "INSERT INTO logs (name, datetime, type, message) VALUES (?, ?, ?, ?)",
            [
                ("warren", "2026-03-02 15:00:00", "trace", "Started: Warren-trading"),
                ("warren", "2026-03-02 15:00:00", "account", "Bought 10 of AAPL"),
                ("george", "2026-03-02 15:00:01", "trace", "Started: George-trading"),
            ],
        )
    conn.close()
    return path


async def test_import_rebuilds_positions_costs_and_history(container, legacy_db):
    accounts = container.accounts
    report = await import_legacy(
        legacy_db, container.db, container.settings, default_traders(container.settings)
    )
    assert report.traders == ["warren"]
    assert (report.trades, report.snapshots, report.events) == (3, 2, 2)
    assert report.warnings == []

    warren = await accounts.get_trader("warren")
    assert warren.name == "Warren" and warren.tagline == "Patience"
    assert warren.strategy == "Old value strategy"
    portfolio = await accounts.portfolio(warren.id)
    assert portfolio.cash == D("8507.4")
    assert [(p.symbol, p.quantity, p.avg_cost) for p in portfolio.positions] == [
        ("AAPL", 5, D("100.2")),
        ("MSFT", 2, D("250.5")),
    ]
    assert portfolio.realized_pnl == (D("110") - D("100.2")) * 5
    trades = await accounts.trades(warren.id)
    assert [(t.side, t.quantity) for t in reversed(trades)] == [("buy", 10), ("sell", 5), ("buy", 2)]
    assert [s.total_value for s in await accounts.snapshots(warren.id)] == [D("10000"), D("10050")]
    assert [e.message for e in await accounts.events(warren.id)] == [
        "Started: Warren-trading",
        "Bought 10 of AAPL",
    ]


async def test_import_skips_traders_with_history_unless_forced(container, legacy_db):
    accounts = container.accounts
    warren = await accounts.get_trader("warren")
    await accounts.buy(warren.id, "AAPL", 1, "new")
    seeds = default_traders(container.settings)

    report = await import_legacy(legacy_db, container.db, container.settings, seeds)
    assert report.skipped == ["warren"]

    report = await import_legacy(legacy_db, container.db, container.settings, seeds, force=True)
    assert report.traders == ["warren"]
    warren = await accounts.get_trader("warren")
    assert len(await accounts.trades(warren.id)) == 3
