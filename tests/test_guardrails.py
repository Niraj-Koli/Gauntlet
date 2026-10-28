"""Trading limits, enforced by AccountService on every order."""

from decimal import Decimal

import pytest

from gauntlet.domain import Guardrails, GuardrailViolation, InvalidOrder

D = Decimal


async def warren(accounts, **guardrails):
    trader = await accounts.get_trader("warren")
    if guardrails:
        trader = await accounts.update_trader(trader.id, guardrails=guardrails)
    return trader


async def test_defaults_cap_a_position_at_40_percent(accounts):
    trader = await warren(accounts)
    await accounts.buy(trader.id, "AAPL", 39, "fits")  # $3,900 of a ~$10,000 portfolio
    with pytest.raises(GuardrailViolation, match="over your limit of 40%"):
        await accounts.buy(trader.id, "AAPL", 2, "too much")
    assert (await accounts.portfolio(trader.id)).positions[0].quantity == 39


async def test_max_order_value(accounts):
    trader = await warren(accounts, max_order_value=500)
    with pytest.raises(GuardrailViolation, match=r"the most a single buy may cost is \$500.00"):
        await accounts.buy(trader.id, "AAPL", 5, "x")
    await accounts.buy(trader.id, "AAPL", 4, "x")


async def test_max_positions(accounts):
    trader = await warren(accounts, max_positions=2)
    await accounts.buy(trader.id, "AAPL", 1, "x")
    await accounts.buy(trader.id, "MSFT", 1, "x")
    with pytest.raises(GuardrailViolation, match="already hold 2 positions"):
        await accounts.buy(trader.id, "SPY", 1, "x")
    await accounts.buy(trader.id, "AAPL", 1, "adding to a held symbol is fine")


async def test_allowed_and_denied_symbols(accounts):
    trader = await warren(accounts, allowed_symbols=["aapl", "msft"], denied_symbols=["MSFT"])
    with pytest.raises(GuardrailViolation, match="isn't in your allowed symbols"):
        await accounts.buy(trader.id, "SPY", 1, "x")
    with pytest.raises(GuardrailViolation, match="denied list"):
        await accounts.buy(trader.id, "MSFT", 1, "x")
    await accounts.buy(trader.id, "AAPL", 1, "x")


async def test_sells_are_allowed_even_for_denied_symbols(accounts):
    trader = await warren(accounts)
    await accounts.buy(trader.id, "MSFT", 2, "x")
    await accounts.update_trader(trader.id, guardrails={"denied_symbols": ["MSFT"]})
    await accounts.sell(trader.id, "MSFT", 2, "getting out")


async def test_trading_hours_only(accounts, market):
    trader = await warren(accounts, trading_hours_only=True)
    market.open = False
    with pytest.raises(GuardrailViolation, match="market is open"):
        await accounts.buy(trader.id, "AAPL", 1, "x")
    market.open = True
    await accounts.buy(trader.id, "AAPL", 1, "x")
    market.open = False
    with pytest.raises(GuardrailViolation):
        await accounts.sell(trader.id, "AAPL", 1, "x")


async def test_limits_can_be_switched_off(accounts):
    trader = await warren(accounts, max_position_pct=None)
    await accounts.buy(trader.id, "AAPL", 90, "all in")


async def test_invalid_guardrails_are_rejected(accounts):
    trader = await warren(accounts)
    with pytest.raises(ValueError):
        await accounts.update_trader(trader.id, guardrails={"max_position_pct": 2})
    with pytest.raises(InvalidOrder):
        await accounts.update_trader(trader.id, status="sleeping")


async def test_the_agent_sees_its_limits(accounts):
    trader = await warren(accounts, max_order_value=2000)
    limits = (await accounts.report(trader.id))["limits"]
    assert limits == {"max_order_value": "2000", "max_position_pct": "0.4", "max_positions": 20}


def test_describe_omits_switched_off_limits():
    assert Guardrails().describe() == {"max_position_pct": "0.4", "max_positions": 20}
    assert Guardrails.for_trader({"trading_hours_only": True, "denied_symbols": ["x"]}).describe() == {
        "max_position_pct": "0.4",
        "max_positions": 20,
        "denied_symbols": ["X"],
        "trading_hours_only": True,
    }
