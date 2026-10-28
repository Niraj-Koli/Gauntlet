"""AccountService: the Phase 0 characterization tests ported to the new service, plus
the fixes for the bugs those tests recorded."""

import asyncio
from decimal import Decimal

import pytest

from gauntlet.domain import InsufficientFunds, InsufficientShares, InvalidOrder, UnknownTrader
from gauntlet.market import InvalidSymbol, PriceUnavailable
from gauntlet.personas import default_traders

D = Decimal
SPREAD = D("0.002")
BUY_AAPL = D("100") * (1 + SPREAD)  # 100.2
SELL_AAPL = D("100") * (1 - SPREAD)  # 99.8


async def warren(accounts):
    return await accounts.get_trader("warren")


# --- traders ----------------------------------------------------------------------------


async def test_the_four_traders_are_seeded_with_starting_cash_and_strategies(accounts):
    traders = await accounts.list_traders()
    assert [t.name for t in traders] == ["Warren", "George", "Ray", "Cathie"]
    for trader in traders:
        assert trader.cash == trader.starting_cash == D("10000")
        assert "named in homage" in trader.strategy
        assert [v.source for v in await accounts.strategy_history(trader.id)] == ["seed"]


async def test_seeding_again_leaves_existing_traders_alone(accounts, settings):
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 1, "test")
    await accounts.ensure_traders(default_traders(settings))
    assert len(await accounts.list_traders()) == 4
    assert (await warren(accounts)).cash < D("10000")


async def test_trader_lookup_is_case_insensitive(accounts):
    assert (await accounts.get_trader("WARREN")).name == "Warren"
    with pytest.raises(UnknownTrader):
        await accounts.get_trader("nobody")


async def test_reset_restores_starting_state(accounts, settings):
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 3, "test")
    await accounts.change_strategy(trader.id, "something else")
    await accounts.record_snapshot(trader.id)
    [seed] = [s for s in default_traders(settings) if s.slug == "warren"]
    await accounts.reset(seed)

    portfolio = await accounts.portfolio(trader.id)
    assert portfolio.cash == D("10000")
    assert portfolio.positions == []
    assert await accounts.trades(trader.id) == []
    assert await accounts.snapshots(trader.id) == []
    assert portfolio.trader.strategy == seed.strategy
    assert [v.source for v in await accounts.strategy_history(trader.id)] == ["seed", "agent", "reset"]


# --- buying -------------------------------------------------------------------------------


async def test_buy_charges_price_plus_spread_and_records_the_trade(accounts):
    trader = await warren(accounts)
    result = await accounts.buy(trader.id, "AAPL", 10, "cheap", run_id=None)

    assert result.trade.side == "buy"
    assert (result.trade.symbol, result.trade.quantity, result.trade.rationale) == ("AAPL", 10, "cheap")
    assert result.trade.price == BUY_AAPL
    assert result.trade.market_price == D("100")
    assert result.portfolio.cash == D("10000") - BUY_AAPL * 10
    [position] = result.portfolio.positions
    assert (position.symbol, position.quantity, position.avg_cost) == ("AAPL", 10, BUY_AAPL)


async def test_buys_accumulate_at_average_cost(accounts, market):
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 2, "a")
    market.prices["AAPL"] = D("110")
    result = await accounts.buy(trader.id, "AAPL", 3, "b")
    [position] = result.portfolio.positions
    assert position.quantity == 5
    assert position.avg_cost == (BUY_AAPL * 2 + D("110") * (1 + SPREAD) * 3) / 5


async def test_symbols_are_normalized(accounts):
    trader = await warren(accounts)
    await accounts.buy(trader.id, " aapl ", 1, "a")
    await accounts.buy(trader.id, "AAPL", 1, "b")
    [position] = (await accounts.portfolio(trader.id)).positions
    assert (position.symbol, position.quantity) == ("AAPL", 2)


async def test_buy_without_enough_cash_is_rejected_and_changes_nothing(accounts):
    trader = await warren(accounts)
    with pytest.raises(InsufficientFunds, match="costs \\$501,000.00"):
        await accounts.buy(trader.id, "SPY", 1_000, "too big")
    portfolio = await accounts.portfolio(trader.id)
    assert portfolio.cash == D("10000")
    assert portfolio.positions == []
    assert await accounts.trades(trader.id) == []


async def test_buy_of_a_symbol_without_a_price_is_rejected(accounts):
    trader = await warren(accounts)
    with pytest.raises(PriceUnavailable):
        await accounts.buy(trader.id, "NOPE", 1, "?")


@pytest.mark.parametrize("symbol", ["", "123", "TOO-LONG-SYMBOL", "AA PL", "$AAPL"])
async def test_buy_of_a_malformed_symbol_is_rejected(accounts, symbol):
    trader = await warren(accounts)
    with pytest.raises(InvalidSymbol):
        await accounts.buy(trader.id, symbol, 1, "?")


@pytest.mark.parametrize("quantity", [-5, 0, 1.5, True, "3", 10_000_000])
async def test_buy_rejects_bad_quantities(accounts, quantity):
    """Phase 0 bug: a negative buy used to add cash."""
    trader = await warren(accounts)
    with pytest.raises(InvalidOrder):
        await accounts.buy(trader.id, "AAPL", quantity, "free money")
    assert (await accounts.portfolio(trader.id)).cash == D("10000")


# --- selling ------------------------------------------------------------------------------


async def test_sell_pays_price_minus_spread_and_books_realized_profit(accounts, market):
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 4, "in")
    market.prices["AAPL"] = D("120")
    result = await accounts.sell(trader.id, "AAPL", 1, "out")

    sell_price = D("120") * (1 - SPREAD)
    assert result.trade.side == "sell"
    assert result.trade.price == sell_price
    assert result.trade.realized_pnl == sell_price - BUY_AAPL
    assert result.portfolio.cash == D("10000") - BUY_AAPL * 4 + sell_price
    assert result.portfolio.positions[0].quantity == 3
    assert result.portfolio.realized_pnl == sell_price - BUY_AAPL


async def test_selling_everything_removes_the_position(accounts):
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 2, "in")
    result = await accounts.sell(trader.id, "AAPL", 2, "out")
    assert result.portfolio.positions == []


async def test_selling_more_than_held_is_rejected(accounts):
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 2, "in")
    with pytest.raises(InsufficientShares, match="only 2 held"):
        await accounts.sell(trader.id, "AAPL", 3, "too many")
    with pytest.raises(InsufficientShares, match="only 0 held"):
        await accounts.sell(trader.id, "MSFT", 1, "never bought")


@pytest.mark.parametrize("quantity", [-5, 0])
async def test_sell_rejects_non_positive_quantities(accounts, quantity):
    """Phase 0 bug: a negative sell used to add shares."""
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 1, "in")
    with pytest.raises(InvalidOrder):
        await accounts.sell(trader.id, "AAPL", quantity, "free shares")


# --- concurrency --------------------------------------------------------------------------


async def test_concurrent_buys_never_overspend(accounts):
    """Phase 0 bug: concurrent read-modify-write could lose updates."""
    trader = await warren(accounts)
    await accounts.update_trader(trader.id, guardrails={"max_position_pct": None})
    cost = BUY_AAPL * 10  # 1,002: nine fit in 10,000
    results = await asyncio.gather(
        *(accounts.buy(trader.id, "AAPL", 10, f"order {i}") for i in range(15)), return_exceptions=True
    )
    filled = [r for r in results if not isinstance(r, BaseException)]
    rejected = [r for r in results if isinstance(r, InsufficientFunds)]
    assert (len(filled), len(rejected)) == (9, 6)
    portfolio = await accounts.portfolio(trader.id)
    assert portfolio.cash == D("10000") - cost * 9
    assert portfolio.positions[0].quantity == 90
    assert len(await accounts.trades(trader.id)) == 9


async def test_concurrent_sells_never_oversell(accounts):
    trader = await warren(accounts)
    await accounts.update_trader(trader.id, guardrails={"max_position_pct": None})
    await accounts.buy(trader.id, "AAPL", 5, "in")
    results = await asyncio.gather(
        *(accounts.sell(trader.id, "AAPL", 2, f"order {i}") for i in range(5)), return_exceptions=True
    )
    assert sum(not isinstance(r, BaseException) for r in results) == 2
    assert (await accounts.portfolio(trader.id)).positions[0].quantity == 1


# --- valuation and reports ----------------------------------------------------------------


async def test_portfolio_is_cash_plus_positions_at_market(accounts, market):
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 10, "a")
    await accounts.buy(trader.id, "MSFT", 2, "b")
    market.prices["AAPL"] = D("110")
    portfolio = await accounts.portfolio(trader.id)
    assert portfolio.holdings_value == D("110") * 10 + D("250") * 2
    assert portfolio.total_value == portfolio.cash + portfolio.holdings_value
    assert portfolio.pnl == portfolio.total_value - D("10000")
    assert portfolio.unrealized_pnl == (D("110") - BUY_AAPL) * 10 + (D("250") - D("250") * (1 + SPREAD)) * 2


async def test_report_describes_the_account_without_changing_anything(accounts):
    """Phase 0 bug: reading the report appended to the value history."""
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 10, "a")
    report = await accounts.report(trader.id)
    await accounts.report(trader.id)

    assert await accounts.snapshots(trader.id) == []
    assert report["name"] == "Warren"
    assert report["cash"] == pytest.approx(10000 - 1002)
    assert report["total_portfolio_value"] == pytest.approx(10000 - 1002 + 1000)
    assert report["total_profit_loss"] == pytest.approx(-2)
    assert report["positions"][0]["symbol"] == "AAPL"
    assert report["recent_transactions"][0]["rationale"] == "a"


async def test_snapshots_are_recorded_explicitly(accounts):
    trader = await warren(accounts)
    await accounts.record_snapshot(trader.id)
    await accounts.buy(trader.id, "AAPL", 10, "a")
    await accounts.record_snapshot(trader.id)
    snapshots = await accounts.snapshots(trader.id)
    assert [s.total_value for s in snapshots] == [D("10000"), D("9998")]


# --- strategy, events and runs ------------------------------------------------------------


async def test_change_strategy_is_saved_versioned_and_logged(accounts):
    trader = await warren(accounts)
    await accounts.change_strategy(trader.id, "  macro  ")
    assert (await warren(accounts)).strategy == "macro"
    assert (await accounts.strategy_history(trader.id))[-1].strategy == "macro"
    assert [e.message for e in await accounts.events(trader.id)][-1] == "Changed strategy"
    with pytest.raises(InvalidOrder):
        await accounts.change_strategy(trader.id, "   ")


async def test_trades_are_logged_in_order(accounts):
    """Phase 0 bug: lines written in the same second came back reversed."""
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 2, "a")
    await accounts.buy(trader.id, "MSFT", 1, "b")
    await accounts.sell(trader.id, "AAPL", 1, "c")
    assert [e.message for e in await accounts.events(trader.id)] == [
        "Bought 2 of AAPL",
        "Bought 1 of MSFT",
        "Sold 1 of AAPL",
    ]
    assert [e.message for e in await accounts.events(trader.id, last_n=2)] == [
        "Bought 1 of MSFT",
        "Sold 1 of AAPL",
    ]


async def test_runs_alternate_between_trading_and_rebalancing(accounts):
    trader = await warren(accounts)
    assert await accounts.next_run_kind(trader.id) == "trade"
    run = await accounts.start_run(trader.id, "trade")
    assert await accounts.next_run_kind(trader.id) == "trade"  # still running
    await accounts.finish_run(run.id, summary="done")
    assert await accounts.next_run_kind(trader.id) == "rebalance"
    run = await accounts.start_run(trader.id, "rebalance")
    await accounts.finish_run(run.id, error="boom")
    assert await accounts.next_run_kind(trader.id) == "trade"


async def test_trades_are_linked_to_their_run(accounts):
    trader = await warren(accounts)
    run = await accounts.start_run(trader.id, "trade")
    result = await accounts.buy(trader.id, "AAPL", 1, "a", run_id=run.id)
    assert result.trade.run_id == run.id
    assert (await accounts.events(trader.id))[-1].run_id == run.id


async def test_what_agents_and_admins_store_is_bounded(accounts):
    from gauntlet.domain import TraderSeed
    from gauntlet.domain.accounts import MAX_RATIONALE_CHARS, MAX_STRATEGY_CHARS

    warren = await accounts.get_trader("warren")
    with pytest.raises(InvalidOrder, match="limited to"):
        await accounts.change_strategy(warren.id, "x" * (MAX_STRATEGY_CHARS + 1))
    result = await accounts.buy(warren.id, "AAPL", 1, "because " * 2000)
    assert len(result.trade.rationale) == MAX_RATIONALE_CHARS

    seed = TraderSeed(slug="big", name="Big", tagline="t", model_name="openai/gpt-5.5", strategy="s")
    with pytest.raises(InvalidOrder, match="at most"):
        await accounts.create_trader(seed, starting_cash=Decimal("1e15"))
