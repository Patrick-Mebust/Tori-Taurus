"""Synthetic first-pullback transitions, depth and time boundaries."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tori_taurus.market_data import Bar
from tori_taurus.setups.first_pullback import PullbackConfig, evaluate_first_pullback

NOW = datetime(2026, 10, 7, 14, tzinfo=UTC)


def sequence():
    values = [
        (10, 10, 9, 10),
        (11, 11, 10, 11),
        (12, 12, 11, 12),
        (12, 12, 11, 11),
        (12, 13, 11, 13),
    ]
    return [
        Bar("TEST", NOW + timedelta(minutes=i), *values, 10, "1m", "synthetic", session="regular")
        for i, values in enumerate(values)
    ]


def result(data, **options):
    return evaluate_first_pullback(
        data,
        as_of=data[-1].timestamp + timedelta(minutes=1),
        config=PullbackConfig(max_extension_percent=20, **options),
    )


def test_impulse_watch_confirmed():
    data = sequence()
    assert result(data[:2])["state"] == "UNAVAILABLE"
    assert result(data[:3])["state"] == "IMPULSE"
    watch = result(data[:4])
    assert watch["state"] == "WATCH" and watch["invalidation_level"] == "10.5"
    report = result(data)
    assert report["state"] == "CONFIRMED" and report["confirmation_level"] == "12"
    assert report["mode"] == "replay"


def test_depth_touch_precedes_confirmation_and_stays_terminal():
    data = sequence()
    data[3] = replace(data[3], low=Decimal("10.5"))
    report = result(data)
    assert report["state"] == "INVALIDATED" and report["confirmed_at"] is None
    assert report["invalidated_at"] == data[3].timestamp.isoformat()


def test_exact_high_does_not_confirm():
    data = sequence()
    data[4] = replace(data[4], close=Decimal(12))
    assert result(data)["state"] == "WATCH"


def test_extension_blocks_confirmation():
    data = sequence()
    report = evaluate_first_pullback(data, as_of=data[-1].timestamp + timedelta(minutes=1))
    assert report["state"] == "EXTENDED" and report["confirmed_at"] is None


def test_window_expiry():
    data = sequence()[:4]
    data += [replace(data[-1], timestamp=NOW + timedelta(minutes=i)) for i in [4, 5]]
    report = result(data, max_pullback_bars=1)
    assert report["state"] == "EXPIRED" and report["expired_at"] == data[-1].timestamp.isoformat()


def test_unqualified_or_zero_volume_impulse():
    data = sequence()
    data[1] = replace(data[1], close=Decimal(10))
    assert result(data)["state"] == "NO_SETUP"
    assert result([replace(b, volume=0) for b in sequence()])["state"] == "NO_SETUP"


def test_stale_unfinished_and_configuration():
    data = sequence()
    for clock in [data[-1].timestamp, data[-1].timestamp + timedelta(minutes=4)]:
        with pytest.raises(ValueError):
            evaluate_first_pullback(data, as_of=clock)
    for options in [
        {"impulse_bars": 1},
        {"max_retracement_percent": 100},
        {"max_pullback_bars": 0},
        {"min_impulse_percent": -1},
    ]:
        with pytest.raises(ValueError):
            PullbackConfig(**options)


def test_zero_volume_does_not_raise_impulse_peak():
    data = sequence()[:3]
    data.append(
        replace(data[-1], timestamp=NOW + timedelta(minutes=3), high=Decimal(100), volume=0)
    )
    data.append(replace(sequence()[3], timestamp=NOW + timedelta(minutes=4)))
    report = result(data)
    assert report["impulse_peak"] == "12"
    assert report["invalidation_level"] == "10.5"
