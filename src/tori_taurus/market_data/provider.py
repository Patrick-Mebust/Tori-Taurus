"""Read-only market provider contract and explicit freshness policy."""

from datetime import datetime, timedelta
from typing import Protocol

from .models import Bar, Quote, utc


class MarketDataProvider(Protocol):
    def get_quote(self, ticker: str) -> Quote: ...
    def get_bars(
        self, ticker: str, start: datetime, end: datetime, interval: str = "1d"
    ) -> list[Bar]: ...


def validate_freshness(quote: Quote, *, now: datetime, max_age: timedelta) -> None:
    """Require live provenance and a timestamp in [now - max_age, now]."""
    if max_age < timedelta(0):
        raise ValueError("Maximum age must be nonnegative")
    age = utc(now) - quote.timestamp
    if quote.mode != "live" or age < timedelta(0) or age > max_age:
        raise ValueError("Quote is not valid current live data")
