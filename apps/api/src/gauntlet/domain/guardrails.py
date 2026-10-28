"""Per-trader trading limits, enforced by AccountService on every order.

A trader's `guardrails` column holds overrides of these defaults; null means defaults.
Sells are never blocked by size or symbol limits, since they only reduce risk.
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .errors import TradingError


class GuardrailViolation(TradingError):
    pass


class Guardrails(BaseModel):
    max_order_value: Decimal | None = Field(default=None, gt=0)
    """Largest cost of a single buy, in dollars."""
    max_position_pct: Decimal | None = Field(default=Decimal("0.4"), gt=0, le=1)
    """Largest share of total portfolio value one position may reach through buying."""
    max_positions: int | None = Field(default=20, gt=0)
    """Most distinct symbols held at once."""
    allowed_symbols: list[str] | None = None
    """If set, the only symbols that may be bought."""
    denied_symbols: list[str] = Field(default_factory=list)
    trading_hours_only: bool = False
    """Reject all orders while the market is closed."""

    @field_validator("allowed_symbols", "denied_symbols", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return [str(s).strip().upper() for s in value] if isinstance(value, list) else value

    @classmethod
    def for_trader(cls, overrides: dict[str, Any] | None) -> "Guardrails":
        return cls.model_validate(overrides or {})

    def describe(self) -> dict[str, Any]:
        """The limits that are switched on, for the agent's account report."""
        limits = self.model_dump(mode="json", exclude_none=True)
        if not limits.get("denied_symbols"):
            limits.pop("denied_symbols", None)
        if not limits.get("trading_hours_only"):
            limits.pop("trading_hours_only", None)
        return limits

    def check_market(self, market_open: bool) -> None:
        if self.trading_hours_only and not market_open:
            raise GuardrailViolation("Orders are only allowed while the market is open")

    def check_buy(
        self,
        symbol: str,
        cost: Decimal,
        position_value_after: Decimal,
        portfolio_value: Decimal,
        held_symbols: set[str],
    ) -> None:
        if symbol in self.denied_symbols:
            raise GuardrailViolation(f"{symbol} is on your denied list and can't be bought")
        if self.allowed_symbols is not None and symbol not in self.allowed_symbols:
            raise GuardrailViolation(
                f"{symbol} isn't in your allowed symbols: {', '.join(self.allowed_symbols)}"
            )
        if self.max_order_value is not None and cost > self.max_order_value:
            raise GuardrailViolation(
                f"This order costs ${cost:,.2f}; the most a single buy may cost is "
                f"${self.max_order_value:,.2f}"
            )
        if (
            self.max_positions is not None
            and symbol not in held_symbols
            and len(held_symbols) >= self.max_positions
        ):
            raise GuardrailViolation(
                f"You already hold {len(held_symbols)} positions, the maximum; "
                f"sell one before adding {symbol}"
            )
        if self.max_position_pct is not None and portfolio_value > 0:
            limit = self.max_position_pct * portfolio_value
            if position_value_after > limit:
                raise GuardrailViolation(
                    f"After this buy {symbol} would be worth ${position_value_after:,.2f}, over your "
                    f"limit of {self.max_position_pct:.0%} of the portfolio (${limit:,.2f}); "
                    "buy fewer shares"
                )
