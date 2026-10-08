"""Optional NYSE schedule classification; no inference of broker availability."""

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .models import Bar, Quote, utc
from .provider import MarketDataProvider


class NyseSessions:
    """Use package-shipped NYSE pre/open/close/post boundaries, not live status."""

    def __init__(self):
        try:
            import pandas_market_calendars as calendars
        except ImportError:
            raise RuntimeError("Install tori-taurus[calendar] for session classification") from None
        self._calendar = calendars.get_calendar("NYSE")
        self._timezone = ZoneInfo("America/New_York")
        self._cache = {}

    def _bounds(self, day: date):
        if day not in self._cache:
            bounds = self._load_bounds(day)
            if len(self._cache) >= 366:
                self._cache.pop(next(iter(self._cache)))
            self._cache[day] = bounds
        return self._cache[day]

    def _load_bounds(self, day: date):
        schedule = self._calendar.schedule(day, day, start="pre", end="post")
        if schedule.empty:
            return None
        row = schedule.iloc[0]
        return tuple(
            utc(row[key].to_pydatetime()) for key in ("pre", "market_open", "market_close", "post")
        )

    def classify(self, timestamp: datetime) -> str:
        timestamp = utc(timestamp)
        bounds = self._bounds(timestamp.astimezone(self._timezone).date())
        if bounds is None:
            return "closed"
        pre, opening, closing, post = bounds
        if pre <= timestamp < opening:
            return "premarket"
        if opening <= timestamp < closing:
            return "regular"
        if closing <= timestamp < post:
            return "postmarket"
        return "closed"


class SessionProvider:
    """Opt-in decorator; preserves prices, source and replay/live provenance."""

    def __init__(self, provider: MarketDataProvider, sessions: NyseSessions):
        self.provider, self.sessions = provider, sessions

    def get_quote(self, ticker: str) -> Quote:
        quote = self.provider.get_quote(ticker)
        return replace(quote, session=self.sessions.classify(quote.timestamp))

    def get_bars(
        self, ticker: str, start: datetime, end: datetime, interval: str = "1d"
    ) -> list[Bar]:
        bars = self.provider.get_bars(ticker, start, end, interval)
        # Daily aggregates span a day: their timestamp is not an intraday session.
        return [
            replace(
                bar,
                session="unknown"
                if bar.interval == "1d"
                else self.sessions.classify(bar.timestamp),
            )
            for bar in bars
        ]
