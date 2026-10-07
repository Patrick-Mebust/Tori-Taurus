"""Known matched-window volumes, completion gates, and DST alignment."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from tori_taurus.indicators import session_features
from tori_taurus.market_data import Bar


def series(day, volumes, *, offset="-04:00", minute=30):
    start = datetime.fromisoformat(f"{day}T09:{minute:02d}:00{offset}")
    return [
        Bar(
            "TEST",
            start + timedelta(minutes=i),
            2,
            3,
            1,
            2,
            v,
            "1m",
            "synthetic",
            session="regular",
        )
        for i, v in enumerate(volumes)
    ]


def report(current, history, **kwargs):
    return session_features(
        current,
        history,
        as_of=current[-1].timestamp + timedelta(minutes=1),
        min_sessions=1,
        acceleration_window=1,
        **kwargs,
    )


def test_known_matched_volume_and_acceleration():
    current = series("2026-10-07", [10, 30])
    # Extra historical bars outside the current window must not enter the mean.
    history = [series("2026-10-06", [10, 10, 1000]), series("2026-10-05", [5, 15, 1000])]
    result = report(current, history)
    assert result["relative_volume"] == "2"
    assert result["volume_acceleration"] == "3"
    assert result["observed_high"] == "3" and result["observed_low"] == "1"
    assert result["observed_volume"] == 40 and result["vwap"] == "2"
    assert result["matching_baseline_sessions"] == 2 and result["mode"] == "replay"


def test_same_local_times_across_dst():
    current = series("2026-03-09", [20, 20])
    historical = series("2026-03-06", [10, 10], offset="-05:00")
    assert report(current, [historical])["relative_volume"] == "2"


def test_shorter_baseline_is_excluded_not_zero_filled():
    current = series("2026-10-07", [10, 30])
    result = report(current, [series("2026-10-06", [100])])
    assert result["relative_volume"] is None
    assert result["excluded_baseline_sessions"] == 1
    assert result["relative_volume_reason"] == "insufficient_matching_sessions"


def test_zero_denominators_and_warmup():
    current = series("2026-10-07", [0, 10])
    result = report(current, [series("2026-10-06", [0, 0])])
    assert result["relative_volume_reason"] == "zero_baseline_volume"
    assert result["volume_acceleration_reason"] == "zero_previous_window_volume"
    result = report(current[:1], [])
    assert result["vwap"] is None and result["volume_acceleration_reason"] == "insufficient_bars"


@pytest.mark.parametrize(
    "case", ["unfinished", "gap", "mixed", "duplicate_date", "future", "daily"]
)
def test_rejects_invalid_windows(case):
    current = series("2026-10-07", [10, 20])
    history = [series("2026-10-06", [10, 10])]
    as_of = current[-1].timestamp + timedelta(minutes=1)
    if case == "unfinished":
        as_of -= timedelta(seconds=1)
    elif case == "gap":
        current[1] = replace(current[1], timestamp=current[1].timestamp + timedelta(minutes=1))
    elif case == "mixed":
        history = [[replace(b, source="other") for b in history[0]]]
    elif case == "duplicate_date":
        history *= 2
    elif case == "future":
        history = [series("2026-10-08", [10, 10])]
    elif case == "daily":
        current = [replace(b, interval="1d") for b in current]
    with pytest.raises(ValueError):
        session_features(current, history, as_of=as_of)


def test_default_minimum_baselines_and_window():
    current = series("2026-10-07", [10, 10, 10, 20, 20, 20])
    history = [series("2026-10-06", [10] * 6)]
    result = session_features(current, history, as_of=current[-1].timestamp + timedelta(minutes=1))
    assert result["relative_volume"] is None
    assert result["volume_acceleration"] == "2"
