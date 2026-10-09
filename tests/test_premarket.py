from dataclasses import replace
from datetime import UTC, datetime, timedelta

from tori_taurus.beta import fetch_live_data
from tori_taurus.market_data import Bar, Quote
from tori_taurus.scanner.dashboard import premarket_research

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def observations():
    bars = [Bar("TEST", NOW - timedelta(minutes=3-i), "2", "2.1", "1.9", "2", 100,
                "1m", "synthetic", mode="live", session="premarket") for i in range(3)]
    quote = Quote("TEST", NOW, "2", "2.01", "synthetic", mode="live", session="premarket")
    return bars, quote


def test_premarket_levels_volume_and_stale_or_wide_spread_gates():
    bars, quote = observations()
    r = premarket_research(bars, quote, NOW)
    assert r["observed_volume"] == 300
    assert r["conditional_entry"] == "2.11" and r["invalidation"] == "1.89"
    assert r["risk_per_share"] == "0.22"
    for q in (replace(quote, timestamp=NOW-timedelta(minutes=2)),
              replace(quote, ask="2.2"), replace(quote, session="regular")):
        assert premarket_research(bars, q, NOW)["conditional_entry"] is None
    assert premarket_research(bars[:2], quote, NOW)["conditional_entry"] is None
    assert premarket_research([replace(b, session="regular") for b in bars], quote, NOW) is None


def test_fetch_premarket_uses_separate_window_and_completed_bars():
    bars, quote = observations()
    calls = []
    class Calendar:
        def _bounds(self, day):
            return (NOW.replace(hour=8), NOW.replace(hour=13, minute=30),
                    NOW.replace(hour=20), NOW.replace(hour=23))
    class Provider:
        def get_quote(self, symbol):
            return quote
        def get_bars(self, symbol, start, end, interval):
            calls.append((start, end, interval))
            return [] if interval == "1d" else bars + [replace(bars[-1], timestamp=NOW)]
    _, _, current = fetch_live_data("TEST", "webull", now=NOW, provider=Provider(),
                                    sessions=Calendar())
    assert current == bars
    assert calls[-1] == (NOW.replace(hour=8), NOW, "1m")
