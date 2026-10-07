from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tori_taurus.market_data import Bar, CsvProvider, Quote, validate_freshness

NOW = datetime(2026, 10, 7, 15, tzinfo=UTC)


def quote(**changes):
    args = {"symbol": " aapl ", "timestamp": NOW, "bid": "1.1", "ask": "1.2", "source": "test"}
    return Quote(**(args | changes))


def test_normalization():
    q = quote(timestamp=datetime.fromisoformat("2026-10-07T10:00:00-05:00"))
    assert q.symbol == "AAPL" and q.timestamp == NOW
    assert q.bid == Decimal("1.1")


@pytest.mark.parametrize(
    "changes",
    [
        {"symbol": "../bad"},
        {"bid": "NaN"},
        {"ask": "Infinity"},
        {"bid": -1},
        {"bid": 2},
        {"timestamp": datetime(2026, 1, 1)},  # noqa: DTZ001 - rejection test
        {"session": "invented"},
        {"mode": "cached"},
        {"source": ""},
    ],
)
def test_bad_quote(changes):
    with pytest.raises(ValueError):
        quote(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"high": 0},
        {"low": 3},
        {"volume": -1},
        {"volume": True},
        {"interval": "invalid"},
        {"close": "NaN"},
    ],
)
def test_bad_bar(changes):
    args = {
        "symbol": "AAPL",
        "timestamp": NOW,
        "open": 1,
        "high": 2,
        "low": 0,
        "close": 1,
        "volume": 10,
        "interval": "1d",
        "source": "test",
    }
    with pytest.raises(ValueError):
        Bar(**(args | changes))


def test_freshness_boundaries():
    validate_freshness(quote(mode="live"), now=NOW, max_age=timedelta(0))
    validate_freshness(
        quote(mode="live", timestamp=NOW - timedelta(seconds=60)),
        now=NOW,
        max_age=timedelta(seconds=60),
    )
    for q in [
        quote(),
        quote(mode="delayed"),
        quote(mode="live", timestamp=NOW - timedelta(seconds=61)),
        quote(mode="live", timestamp=NOW + timedelta(seconds=1)),
    ]:
        with pytest.raises(ValueError):
            validate_freshness(q, now=NOW, max_age=timedelta(seconds=60))
    with pytest.raises(ValueError):
        validate_freshness(quote(mode="live"), now=NOW, max_age=timedelta(seconds=-1))


def test_csv_replay(tmp_path):
    q, b = tmp_path / "quotes.csv", tmp_path / "bars.csv"
    q.write_text("symbol,timestamp,bid,ask,mode\nAAPL,2026-10-07T15:00:00Z,1,2,live\n")
    b.write_text(
        "symbol,timestamp,open,high,low,close,volume,interval\n"
        "AAPL,2026-10-07T15:01:00Z,1,2,0,1,10,1m\n"
        "AAPL,2026-10-07T15:00:00Z,1,2,0,1,10,1m\n"
    )
    provider = CsvProvider(q, b)
    assert provider.get_quote("aapl").mode == "replay"
    bars = provider.get_bars("aapl", NOW, NOW + timedelta(minutes=1), "1m")
    assert len(bars) == 1 and bars[0].timestamp == NOW
    with pytest.raises(LookupError):
        provider.get_quote("MSFT")
    with pytest.raises(ValueError):
        provider.get_bars("aapl", NOW, NOW)
    with pytest.raises(ValueError):
        provider.get_bars("aapl", NOW, NOW + timedelta(days=1), "bad")
    b.write_text(b.read_text() + "AAPL,2026-10-07T15:00:00Z,1,2,0,1,10,1m\n")
    with pytest.raises(ValueError, match="Duplicate"):
        CsvProvider(q, b)
