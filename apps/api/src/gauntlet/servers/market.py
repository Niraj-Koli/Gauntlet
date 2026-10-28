"""MCP server for share prices, served over streamable HTTP by the API. Traders use it
when there's no Massive key; with one they get Massive's own, richer MCP server."""

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from ..market import MarketDataProvider, normalize_symbol


def build_market_server(market: MarketDataProvider, security: TransportSecuritySettings) -> FastMCP:
    mcp = FastMCP(
        "market_server",
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=security,
    )

    @mcp.tool()
    async def lookup_share_price(symbol: str) -> float:
        """This tool provides the current price of the given stock symbol.

        Args:
            symbol: the symbol of the stock
        """
        return float(await market.get_price(normalize_symbol(symbol)))

    return mcp
