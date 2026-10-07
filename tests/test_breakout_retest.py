"""Frozen-level and distinct-bar transition tests, using synthetic candles."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tori_taurus.market_data import Bar
from tori_taurus.setups import BreakoutConfig, evaluate_breakout_retest

NOW = datetime(2026, 10, 7, 14, tzinfo=UTC)


def sequence():
    values = [
        (9, 10, 8, 9),
        (10, 11, 10, 11),
        (11, Decimal("10.8"), Decimal("9.99"), Decimal("10.5")),
        (11, Decimal("11.2"), Decimal("10.5"), 11),
    ]
    values[2] = (Decimal("10.5"), Decimal("10.8"), Decimal("9.99"), Decimal("10.5"))
    return [
        Bar("TEST", NOW + timedelta(minutes=i), *ohlc, 10, "1m", "synthetic", session="regular")
        for i, ohlc in enumerate(values)
    ]


def result(data, extension=20):
    return evaluate_breakout_retest(
        data,
        as_of=data[-1].timestamp + timedelta(minutes=1),
        config=BreakoutConfig(lookback_bars=1, max_extension_percent=Decimal(extension)),
    )


def test_distinct_breakout_retest_confirmation():
    data = sequence()
    assert result(data[:1])["state"] == "UNAVAILABLE"
    assert result(data[:2])["state"] == "WATCH"
    assert result(data[:3])["state"] == "RETEST"
    report = result(data)
    assert report["state"] == "CONFIRMED" and report["resistance_level"] == "10"
    assert report["invalidation_level"] == "9.950"
    assert report["confirmed_at"] == data[3].timestamp.isoformat()
    assert report["mode"] == "replay"


def test_anchor_boundary_has_priority():
    data = sequence()
    data[2] = replace(data[2], low=Decimal("9.95"))
    report = result(data)
    assert report["state"] == "INVALIDATED" and report["reason"] == "anchor_touched"
    assert report["retest_at"] is None and report["confirmed_at"] is None


def test_close_below_level_and_terminal_state():
    data = sequence()
    data[2] = replace(data[2], close=Decimal("9.99"))
    report = result(data)
    assert report["state"] == "INVALIDATED" and report["reason"] == "close_below_resistance"
    assert report["invalidated_at"] == data[2].timestamp.isoformat()


def test_extension_blocks_confirmation():
    report = result(sequence(), extension=3)
    assert report["state"] == "EXTENDED" and report["confirmed_at"] is None
    assert report["retest_at"] is not None


def test_exact_high_does_not_confirm_or_move_resistance():
    data = sequence()
    data[3] = replace(data[3], open=Decimal("10.8"), close=Decimal("10.8"))
    assert result(data)["state"] == "RETEST"
    assert result(data)["resistance_level"] == "10"


def test_no_breakout_at_equality_or_zero_volume():
    data = sequence()[:2]
    data[1] = replace(data[1], close=Decimal(10))
    assert result(data)["state"] == "NO_SETUP"
    data[1] = replace(sequence()[1], volume=0)
    assert result(data)["state"] == "NO_SETUP"
    assert result([replace(b, volume=0) for b in sequence()])["state"] == "UNAVAILABLE"


def test_input_gates_and_config():
    data = sequence()
    for clock in [data[-1].timestamp, data[-1].timestamp + timedelta(minutes=4)]:
        with pytest.raises(ValueError):
            evaluate_breakout_retest(data, as_of=clock)
    for config in [
        {"lookback_bars": 0},
        {"lookback_bars": True},
        {"retest_tolerance_percent": 100},
        {"max_extension_percent": -1},
    ]:
        with pytest.raises(ValueError):
            BreakoutConfig(**config)
