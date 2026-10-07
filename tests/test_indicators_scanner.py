"""Hand-calculated indicator values and research-filter boundaries."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tori_taurus.indicators import atr, ema, rsi, vwap
from tori_taurus.market_data import Bar
from tori_taurus.scanner import ScanConfig, evaluate_daily, scan_daily

NOW = datetime(2026, 10, 7, 14, tzinfo=UTC)


def bars(closes, *, interval="1d", volumes=None):
    return [
        Bar(
            "TEST",
            NOW + timedelta(days=i) if interval == "1d" else NOW + timedelta(minutes=i),
            c,
            c,
            c,
            c,
            volumes[i] if volumes else 10,
            interval,
            "synthetic",
            session="regular",
        )
        for i, c in enumerate(closes)
    ]


def test_known_ema_seed_and_update():
    assert ema(bars([1, 2]), 3) is None
    assert ema(bars([1, 2, 3]), 3) == Decimal(2)
    assert ema(bars([1, 2, 3, 4, 5]), 3) == Decimal(4)


def test_known_wilder_rsi():
    # Changes +2,-1 => initial gain=1, loss=.5 => RSI=66 2/3.
    value = rsi(bars([1, 3, 2]), 2)
    assert abs(value - Decimal("66.66666666666666666666666667")) < Decimal("1e-24")
    # Next +1 => smoothed gain=1, loss=.25 => RSI=80.
    assert rsi(bars([1, 3, 2, 3]), 2) == 80
    assert rsi(bars([1, 2, 3]), 2) == 100
    assert rsi(bars([3, 2, 1]), 2) == 0
    assert rsi(bars([2, 2, 2]), 2) == 50
    assert rsi(bars([1, 2]), 2) is None


def test_known_atr_gap_and_smoothing():
    data = bars([1, 4, 6])
    data[0] = replace(data[0], low=Decimal(0), high=Decimal(2))
    # TRs = 2,3,2; first ATR2=2.5; next=2.25.
    assert atr(data[:2], 2) == Decimal("2.5")
    assert atr(data, 2) == Decimal("2.25")
    assert atr(data[:1], 2) is None


def test_known_vwap_and_zero_volume():
    assert vwap(bars([1, 3], interval="1m", volumes=[10, 30])) == Decimal("2.5")
    assert vwap(bars([1, 3], interval="1m", volumes=[0, 0])) is None
    with pytest.raises(ValueError):
        vwap(bars([1, 3]))
    data = bars([1, 3], interval="1m")
    for bad in [
        replace(data[1], session="unknown"),
        replace(data[1], timestamp=data[1].timestamp + timedelta(days=1)),
    ]:
        with pytest.raises(ValueError):
            vwap([data[0], bad])


@pytest.mark.parametrize("function", [ema, rsi, atr])
def test_period_and_input_validation(function):
    for period in [0, -1, True]:
        with pytest.raises(ValueError):
            function(bars([1, 2]), period)
    for data in [
        [],
        bars([1, 2])[::-1],
        bars([1, 2])[:1] * 2,
        [bars([1])[0], replace(bars([1, 2])[1], source="other")],
    ]:
        with pytest.raises(ValueError):
            function(data, 2)


def test_scanner_boundaries_and_baseline_excludes_latest():
    data = bars([1, 1, 2], volumes=[10, 30, 40])
    result = evaluate_daily(
        data,
        as_of=data[-1].timestamp,
        config=ScanConfig(volume_lookback=2, min_relative_volume=Decimal(2)),
    )
    assert result["candidate"] and result["mode"] == "replay"
    assert result["features"]["daily_relative_volume"] == "2"
    assert result["features"]["change_percent"] == "100"
    assert result["features"]["ema5"] is None
    capped = bars([4, 5])
    assert "price_outside_range" in evaluate_daily(capped, as_of=capped[-1].timestamp)["reasons"]


def test_missing_baseline_and_zero_close_are_explicit():
    data = bars([0, 2], volumes=[0, 20])
    result = evaluate_daily(
        data,
        as_of=data[-1].timestamp,
        config=ScanConfig(volume_lookback=1, min_relative_volume=Decimal(1)),
    )
    assert not result["candidate"]
    assert result["features"]["gap_percent"] is None
    assert result["reasons"] == ["change_unavailable", "relative_volume_unavailable"]


def test_scanner_rejects_lookahead_and_wrong_interval():
    with pytest.raises(ValueError):
        evaluate_daily(bars([1, 2]), as_of=NOW)
    with pytest.raises(ValueError):
        evaluate_daily(bars([1, 2], interval="1m"), as_of=NOW + timedelta(days=1))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_price": 0},
        {"max_price": 0},
        {"min_volume": -1},
        {"volume_lookback": 0},
        {"min_change_percent": "NaN"},
        {"min_relative_volume": -1},
    ],
)
def test_invalid_scan_configuration(kwargs):
    with pytest.raises(ValueError):
        ScanConfig(**kwargs)


def test_batch_scan_retains_rejections_and_order():
    eligible = bars([1, 2])
    expensive = [replace(b, symbol="HIGH") for b in bars([5, 6])]
    results = scan_daily({"TEST": eligible, "HIGH": expensive}, as_of=eligible[-1].timestamp)
    assert [r["symbol"] for r in results] == ["HIGH", "TEST"]
    assert [r["candidate"] for r in results] == [False, True]
    with pytest.raises(ValueError):
        scan_daily({"WRONG": eligible}, as_of=eligible[-1].timestamp)
