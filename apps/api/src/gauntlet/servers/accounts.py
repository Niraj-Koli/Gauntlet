"""MCP server for a trader's own account, served over streamable HTTP by the API.

None of the tools take an account name: the account comes from the caller's token.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from ..db import Event
from ..domain import AccountService, TradeResult, TradingError
from ..market import MarketDataError
from ..security import TraderIdentity
from .auth import identity_from


def _trade_summary(result: TradeResult, report: dict) -> str:
    trade = result.trade
    verb = "Bought" if trade.side == "buy" else "Sold"
    total = trade.price * trade.quantity
    return (
        f"Completed. {verb} {trade.quantity} {trade.symbol} at ${trade.price:,.2f} "
        f"(total ${total:,.2f}). Cash is now ${result.portfolio.cash:,.2f}.\n"
        f"Latest details:\n{json.dumps(report)}"
    )


@asynccontextmanager
async def _logging_rejections(
    accounts: AccountService, identity: TraderIdentity, order: str
) -> AsyncIterator[None]:
    """Record a rejected order in the activity log, then let the error reach the agent."""
    try:
        yield
    except (TradingError, MarketDataError) as e:
        event = Event(
            trader_id=identity.trader_id,
            run_id=identity.run_id,
            kind="account",
            message=f"Rejected {order}: {e}",
        )
        await accounts.log_events([event])
        raise


def build_accounts_server(accounts: AccountService, security: TransportSecuritySettings) -> FastMCP:
    mcp = FastMCP(
        "accounts_server",
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=security,
    )

    @mcp.tool()
    async def get_balance(ctx: Context) -> float:
        """Get the cash balance of your account."""
        trader = await accounts.get_trader_by_id(identity_from(ctx).trader_id)
        return float(round(trader.cash, 2))

    @mcp.tool()
    async def get_holdings(ctx: Context) -> dict[str, int]:
        """Get the shares you hold, as symbol -> quantity."""
        portfolio = await accounts.portfolio(identity_from(ctx).trader_id)
        return {p.symbol: p.quantity for p in portfolio.positions}

    @mcp.tool()
    async def get_account(ctx: Context) -> dict:
        """Get your full account: cash, positions at current prices, profit and recent trades."""
        return await accounts.report(identity_from(ctx).trader_id)

    @mcp.tool()
    async def buy_shares(symbol: str, quantity: int, rationale: str, ctx: Context) -> str:
        """Buy shares of a stock with your cash.

        Args:
            symbol: The ticker symbol of the stock
            quantity: The number of shares to buy (a positive whole number)
            rationale: The rationale for the purchase and fit with your strategy
        """
        identity = identity_from(ctx)
        async with _logging_rejections(accounts, identity, f"buy of {quantity} {symbol}"):
            result = await accounts.buy(
                identity.trader_id, symbol, quantity, rationale, run_id=identity.run_id
            )
        return _trade_summary(result, await accounts.report(identity.trader_id))

    @mcp.tool()
    async def sell_shares(symbol: str, quantity: int, rationale: str, ctx: Context) -> str:
        """Sell shares of a stock you hold.

        Args:
            symbol: The ticker symbol of the stock
            quantity: The number of shares to sell (a positive whole number)
            rationale: The rationale for the sale and fit with your strategy
        """
        identity = identity_from(ctx)
        async with _logging_rejections(accounts, identity, f"sell of {quantity} {symbol}"):
            result = await accounts.sell(
                identity.trader_id, symbol, quantity, rationale, run_id=identity.run_id
            )
        return _trade_summary(result, await accounts.report(identity.trader_id))

    @mcp.tool()
    async def change_strategy(strategy: str, ctx: Context) -> str:
        """At your discretion, if you choose to, call this to change your investment strategy
        for the future.

        Args:
            strategy: Your new investment strategy
        """
        identity = identity_from(ctx)
        await accounts.change_strategy(identity.trader_id, strategy, source="agent", run_id=identity.run_id)
        return "Changed strategy"

    return mcp
