"""Pivot recognition timing, frozen thresholds, and invalidation precedence."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tori_taurus.market_data import Bar
from tori_taurus.setups import HigherLowConfig, evaluate_higher_low

NOW = datetime(2026, 10, 7, 14, tzinfo=UTC)


def sequence():
    lows = [10, 9, 11, 10, 11, 12]
    highs = [12, 12, 13, 12, 14, 14]
    closes = [11, 10, 12, 11, 13, 14]
    return [
        Bar(
            "TEST",
            NOW + timedelta(minutes=i),
            close,
            high,
            low,
            close,
            10,
            "1m",
            "synthetic",
            session="regular",
        )
        for i, (low, high, close) in enumerate(zip(lows, highs, closes, strict=True))
    ]


def result(data, **kwargs):
    return evaluate_higher_low(
        data,
        as_of=data[-1].timestamp + timedelta(minutes=1),
        config=HigherLowConfig(max_extension_percent=20, **kwargs),
    )


def test_delayed_recognition_and_separate_confirmation():
    data = sequence()
    assert result(data[:4])["state"] == "NO_SETUP"
    watch = result(data[:5])
    assert watch["state"] == "WATCH" and watch["confirmed_at"] is None
    assert watch["higher_low_at"] == data[3].timestamp.isoformat()
    assert watch["identified_at"] == (data[4].timestamp + timedelta(minutes=1)).isoformat()
    assert watch["confirmation_level"] == "13" and watch["invalidation_level"] == "10"
    report = result(data)
    assert report["state"] == "CONFIRMED" and report["mode"] == "replay"
    assert report["confirmed_at"] == data[5].timestamp.isoformat()


def test_confirmation_does_not_move_prior_level():
    data = sequence()
    data[5] = replace(data[5], high=Decimal(20))
    assert result(data)["confirmation_level"] == "13"


def test_anchor_touch_invalidates_before_confirmation():
    data = sequence()
    data[5] = replace(data[5], low=Decimal(10))
    report = result(data)
    assert report["state"] == "INVALIDATED" and report["confirmed_at"] is None
    data.append(replace(sequence()[5], timestamp=NOW + timedelta(minutes=6)))
    assert result(data)["invalidated_at"] == report["invalidated_at"]


def test_equality_and_extension_block_confirmation():
    data = sequence()
    data[5] = replace(data[5], close=Decimal(13))
    assert result(data)["state"] == "WATCH"
    original = sequence()
    report = evaluate_higher_low(original, as_of=original[-1].timestamp + timedelta(minutes=1))
    assert report["state"] == "EXTENDED" and report["confirmed_at"] is None


def test_improvement_requirement_and_zero_volume():
    assert result(sequence(), min_low_improvement_percent=20)["state"] == "NO_SETUP"
    assert result([replace(b, volume=0) for b in sequence()])["state"] == "NO_SETUP"


def test_history_clock_and_configuration_gates():
    data = sequence()
    assert result(data[:2])["state"] == "UNAVAILABLE"
    for clock in [data[-1].timestamp, data[-1].timestamp + timedelta(minutes=4)]:
        with pytest.raises(ValueError):
            evaluate_higher_low(data, as_of=clock)
    for config in [
        {"pivot_width": 0},
        {"pivot_width": True},
        {"min_low_improvement_percent": -1},
        {"max_extension_percent": -1},
    ]:
        with pytest.raises(ValueError):
            HigherLowConfig(**config)
