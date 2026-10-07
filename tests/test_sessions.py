"""Actual calendar boundary checks; synthetic provider records."""

from datetime import UTC, datetime, timedelta

import pytest

from tori_taurus.market_data import Bar, Quote
from tori_taurus.market_data.sessions import NyseSessions, SessionProvider

pytest.importorskip("pandas_market_calendars")


@pytest.fixture(scope="module")
def sessions():
    return NyseSessions()


@pytest.mark.parametrize(
    "timestamp,expected",
    [
        ("2026-10-07T07:59:59Z", "closed"),
        ("2026-10-07T08:00:00Z", "premarket"),
        ("2026-10-07T13:29:59Z", "premarket"),
        ("2026-10-07T13:30:00Z", "regular"),
        ("2026-10-07T19:59:59Z", "regular"),
        ("2026-10-07T20:00:00Z", "postmarket"),
        ("2026-10-08T00:00:00Z", "closed"),
        ("2026-07-03T15:00:00Z", "closed"),  # Independence Day observed
        ("2026-12-25T15:00:00Z", "closed"),
        ("2026-10-10T15:00:00Z", "closed"),
        ("2026-11-27T17:59:59Z", "regular"),
        ("2026-11-27T18:00:00Z", "postmarket"),
        ("2026-11-27T22:00:00Z", "closed"),  # early-close extended session ends 17 ET
        ("2026-03-06T14:30:00Z", "regular"),  # before DST
        ("2026-03-09T13:30:00Z", "regular"),  # after DST
        ("2026-10-30T13:30:00Z", "regular"),
        ("2026-11-02T14:30:00Z", "regular"),
        ("2025-01-09T15:00:00Z", "closed"),  # Carter national day of mourning
    ],
)
def test_calendar_boundaries(sessions, timestamp, expected):
    assert sessions.classify(datetime.fromisoformat(timestamp)) == expected


def test_equivalent_timezones_and_naive_rejection(sessions):
    assert sessions.classify(datetime.fromisoformat("2026-10-07T09:30:00-04:00")) == "regular"
    with pytest.raises(ValueError, match="timezone"):
        sessions.classify(datetime(2026, 10, 7))  # noqa: DTZ001 - rejection test


def test_decorator_preserves_provenance_and_daily_ambiguity(sessions):
    timestamp = datetime(2026, 10, 7, 14, tzinfo=UTC)
    quote = Quote("AAPL", timestamp, 1, 2, "synthetic", mode="replay")
    intraday = Bar("AAPL", timestamp, 1, 2, 0, 1, 10, "1m", "synthetic")
    daily = Bar("AAPL", timestamp, 1, 2, 0, 1, 10, "1d", "synthetic")

    class Provider:
        def get_quote(self, ticker):
            return quote

        def get_bars(self, ticker, start, end, interval="1d"):
            return [daily] if interval == "1d" else [intraday]

    decorated = SessionProvider(Provider(), sessions)
    result = decorated.get_quote("AAPL")
    assert result.session == "regular"
    assert result.source == quote.source and result.mode == "replay"
    assert result.bid == quote.bid and result.timestamp == quote.timestamp
    assert quote.session == "unknown"  # original frozen records are unchanged
    assert (
        decorated.get_bars("AAPL", timestamp, timestamp + timedelta(days=1))[0].session == "unknown"
    )
    assert (
        decorated.get_bars("AAPL", timestamp, timestamp + timedelta(days=1), "1m")[0].session
        == "regular"
    )
