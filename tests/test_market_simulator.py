"""Characterization tests for the simulated price feed: these pin today's behaviour so
the market-data refactor can't silently change the prices the traders see."""

from datetime import UTC, datetime, timedelta

import pytest

from gauntlet.market.simulator import SWING, _seed, simulated_price

JAN = datetime(2026, 1, 1, 15, 30, tzinfo=UTC)
JUN = datetime(2026, 6, 1, 15, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("ticker", "january", "june"),
    [
        ("AAPL", 149.91, 166.16),
        ("MSFT", 128.9, 145.27),
        ("SPY", 230.16, 249.75),
        ("IBIT", 262.69, 210.65),
    ],
)
def test_golden_prices(ticker, january, june):
    assert simulated_price(ticker, JAN) == january
    assert simulated_price(ticker, JUN) == june


def test_same_inputs_give_same_price():
    assert simulated_price("NVDA", JAN) == simulated_price("NVDA", JAN)


def test_ticker_is_case_insensitive():
    assert simulated_price("aapl", JAN) == simulated_price("AAPL", JAN)


def test_prices_stay_within_the_swing_of_their_base():
    for ticker in ["AAPL", "MSFT", "SPY", "IBIT", "TSLA", "XYZ"]:
        base = 20 + _seed(ticker) % 480
        for day in range(0, 720, 7):
            price = simulated_price(ticker, JAN + timedelta(days=day))
            assert base * (1 - SWING) - 0.01 <= price <= base * (1 + SWING) + 0.01


def test_prices_move_smoothly_minute_to_minute():
    for minute in range(60):
        now = JAN + timedelta(minutes=minute)
        before = simulated_price("AAPL", now)
        after = simulated_price("AAPL", now + timedelta(minutes=1))
        assert abs(after - before) / before < 0.01


def test_prices_are_rounded_to_cents():
    price = simulated_price("AAPL", JAN + timedelta(seconds=12345))
    assert round(price, 2) == price


def test_defaults_to_now():
    assert simulated_price("AAPL") > 0
