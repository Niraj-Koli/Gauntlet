"""Column types that behave the same on Postgres (Supabase) and SQLite."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Dialect, Numeric, String
from sqlalchemy.types import TypeDecorator, TypeEngine

MONEY_QUANTUM = Decimal("0.000001")


def to_money(value: Decimal | float | int | str) -> Decimal:
    """Exact decimal rounded to the precision the database stores."""
    return Decimal(str(value)).quantize(MONEY_QUANTUM)


class Money(TypeDecorator[Decimal]):
    """Exact decimal money: NUMERIC(20, 6) on Postgres, decimal text on SQLite, which
    has no exact decimal type and would otherwise round-trip through float."""

    impl = Numeric(20, 6)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(32))
        return dialect.type_descriptor(Numeric(20, 6, asdecimal=True))

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        money = to_money(value)
        return str(money) if dialect.name == "sqlite" else money

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        return None if value is None else to_money(value)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC timestamps. SQLite drops the offset, so it's stored as naive UTC
    and reattached on load."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime; use timezone-aware UTC")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)
