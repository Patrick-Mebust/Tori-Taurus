"""End-to-end joins of synthetic market models, features and setup states."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from tori_taurus.market_data import Bar, Quote
from tori_taurus.report import build_report, report_from_provider

NOW = datetime(2026, 10, 7, 14, tzinfo=UTC)


def inputs():
    current = [
        Bar(
            "TEST",
            NOW - timedelta(minutes=6 - i),
            2,
            3,
            1,
            2,
            10,
            "1m",
            "synthetic",
            session="regular",
        )
        for i in range(6)
    ]
    daily = [
        Bar("TEST", NOW - timedelta(days=2 - i), 1 + i, 2 + i, 1 + i, 2 + i, 100, "1d", "synthetic")
        for i in range(2)
    ]
    quote = Quote("TEST", NOW, 2, 3, "synthetic", mode="live")
    return quote, daily, current


def test_join_and_json_serialization():
    quote, daily, current = inputs()
    report = build_report("test", as_of=NOW, quote=quote, daily_bars=daily, session_bars=current)
    assert report["quote"]["fresh"] and report["daily_scan"]["candidate"]
    assert report["intraday"]["mode"] == "replay"
    assert len(report["setups"]) == 4
    assert report["risk"]["status"] == "unavailable"
    assert not report["decision"]["ready_to_trade"]
    assert json.loads(json.dumps(report))["schema_version"] == "1.0"


def test_missing_data_stays_explicit():
    report = build_report("TEST", as_of=NOW)
    assert report["quote"]["status"] == "unavailable"
    assert report["daily_scan"]["status"] == "unavailable"
    assert all(s["state"] == "UNAVAILABLE" for s in report["setups"].values())


def test_stale_observations_do_not_become_live():
    quote, daily, current = inputs()
    report = build_report(
        "TEST", as_of=NOW + timedelta(hours=1), quote=quote, daily_bars=daily, session_bars=current
    )
    assert not report["quote"]["fresh"]
    assert all(s["state"] == "UNAVAILABLE" for s in report["setups"].values())
    assert "no_eligible_setup_observations" in report["decision"]["blockers"]


def test_replay_quote_never_passes_live_gate():
    quote, _, _ = inputs()
    report = build_report("TEST", as_of=NOW, quote=replace(quote, mode="replay"))
    assert "no_fresh_live_quote" in report["decision"]["blockers"]


@pytest.mark.parametrize("case", ["symbol", "source", "future", "unfinished"])
def test_invalid_observations_fail(case):
    quote, daily, current = inputs()
    if case == "symbol":
        quote = replace(quote, symbol="OTHER")
    elif case == "source":
        quote = replace(quote, source="other")
    elif case == "future":
        daily[-1] = replace(daily[-1], timestamp=NOW + timedelta(days=1))
    else:
        current[-1] = replace(current[-1], timestamp=NOW - timedelta(seconds=30))
    with pytest.raises(ValueError):
        build_report("TEST", as_of=NOW, quote=quote, daily_bars=daily, session_bars=current)


def test_provider_flow_and_unlabeled_data_gate():
    quote, daily, current = inputs()
    calls = []

    class Provider:
        def get_quote(self, ticker):
            calls.append(("quote", ticker))
            return quote

        def get_bars(self, ticker, start, end, interval="1d"):
            calls.append(("bars", interval))
            return daily if interval == "1d" else current

    args = {
        "as_of": NOW,
        "history_start": NOW - timedelta(days=7),
        "session_start": NOW - timedelta(minutes=6),
    }
    report = report_from_provider(Provider(), "TEST", **args)
    assert len(calls) == 3 and report["intraday"]["bar_count"] == 6
    current[0] = replace(current[0], session="unknown")
    with pytest.raises(ValueError, match="label"):
        report_from_provider(Provider(), "TEST", **args)
