"""NYSE trading hours from the local exchange calendar, used when the data provider can't
tell us. Holidays and early closes are included."""

import logging
from datetime import UTC, datetime
from functools import lru_cache

import pandas as pd

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _nyse():
    import exchange_calendars  # slow to import, so only when first needed

    return exchange_calendars.get_calendar("XNYS")


def nyse_is_open(now: datetime | None = None) -> bool:
    """Whether NYSE is in its regular session; False if the calendar can't say."""
    now = now or datetime.now(UTC)
    try:
        calendar = _nyse()
        minute = pd.Timestamp(now).tz_convert("UTC").floor("min")
        if not isinstance(minute, pd.Timestamp):
            return False
        if not calendar.first_minute <= minute <= calendar.last_minute:
            return False
        return bool(calendar.is_open_on_minute(minute))
    except Exception:
        logger.exception("NYSE calendar check failed; treating the market as closed")
        return False
