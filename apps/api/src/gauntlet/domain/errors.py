"""Domain errors. They subclass ValueError and their messages are written for the agent,
since MCP tools pass them straight back as the tool error."""


class TradingError(ValueError):
    pass


class UnknownTrader(TradingError):
    pass


class InvalidOrder(TradingError):
    pass


class InsufficientFunds(TradingError):
    pass


class InsufficientShares(TradingError):
    pass
