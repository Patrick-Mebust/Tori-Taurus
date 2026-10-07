"""Explicit first-reclaim transitions and invalidation precedence."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tori_taurus.market_data import Bar
from tori_taurus.setups import ReclaimConfig, evaluate_vwap_reclaim

NOW = datetime(2026, 10, 7, 14, tzinfo=UTC)


def sequence():
    # Bar 0 typical price 10, close9 below VWAP; bar1 typical11, close12 reclaims.
    return [
        Bar("TEST", NOW, 10, 12, 9, 9, 10, "1m", "synthetic", session="regular"),
        Bar(
            "TEST",
            NOW + timedelta(minutes=1),
            10,
            12,
            9,
            12,
            10,
            "1m",
            "synthetic",
            session="regular",
        ),
        Bar(
            "TEST",
            NOW + timedelta(minutes=2),
            12,
            13,
            12,
            13,
            10,
            "1m",
            "synthetic",
            session="regular",
        ),
    ]


def result(bars, limit=100):
    return evaluate_vwap_reclaim(
        bars,
        as_of=bars[-1].timestamp + timedelta(minutes=1),
        config=ReclaimConfig(max_extension_percent=Decimal(limit)),
    )


def test_no_setup_watch_confirmed():
    data = sequence()
    assert result(data[:1])["state"] == "NO_SETUP"
    watch = result(data[:2])
    assert watch["state"] == "WATCH" and watch["confirmed_at"] is None
    assert watch["confirmation_level"] == "12" and watch["invalidation_level"] == "9"
    confirmed = result(data)
    assert confirmed["state"] == "CONFIRMED"
    assert confirmed["confirmed_at"] == data[-1].timestamp.isoformat()
    assert confirmed["mode"] == "replay"


def test_extension_blocks_confirmation():
    assert result(sequence(), limit=1)["state"] == "EXTENDED"
    assert result(sequence(), limit=1)["confirmed_at"] is None


def test_anchor_touch_invalidates_before_confirmation():
    data = sequence()
    data[2] = replace(data[2], low=Decimal(9))
    report = result(data)
    assert report["state"] == "INVALIDATED" and report["reason"] == "anchor_low_touched"
    assert report["confirmed_at"] is None


def test_close_below_vwap_invalidates_and_does_not_rearm():
    data = sequence()
    data.append(
        Bar(
            "TEST",
            NOW + timedelta(minutes=3),
            11,
            12,
            10,
            10,
            10,
            "1m",
            "synthetic",
            session="regular",
        )
    )
    report = result(data)
    assert report["state"] == "INVALIDATED" and report["reason"] == "close_below_vwap"
    assert report["confirmed_at"] is not None
    data.append(replace(data[2], timestamp=NOW + timedelta(minutes=4)))
    assert result(data)["invalidated_at"] == report["invalidated_at"]


def test_exact_confirmation_boundary_does_not_confirm():
    data = sequence()
    data[2] = replace(data[2], close=Decimal(12))
    assert result(data)["state"] == "WATCH"


def test_zero_volume_has_no_setup_levels():
    report = result([replace(b, volume=0) for b in sequence()])
    assert report["state"] == "UNAVAILABLE" and report["vwap"] is None
    assert report["confirmation_level"] is None


def test_stale_and_unfinished_inputs_fail():
    data = sequence()
    for as_of in [data[-1].timestamp, data[-1].timestamp + timedelta(minutes=4)]:
        with pytest.raises(ValueError):
            evaluate_vwap_reclaim(data, as_of=as_of)


def test_invalid_config_and_unknown_session():
    with pytest.raises(ValueError):
        ReclaimConfig(max_extension_percent=-1)
    with pytest.raises(ValueError):
        ReclaimConfig(max_observation_age=timedelta(seconds=-1))
    with pytest.raises(ValueError):
        result([replace(b, session="unknown") for b in sequence()])
