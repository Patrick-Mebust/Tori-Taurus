"""Selected thresholds must be enforced before bounded candidate inspection."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tori_taurus.market_data import Bar
from tori_taurus.market_data.webull import WebullProvider
from tori_taurus.scanner import evaluate_daily
from tori_taurus.scanner.dashboard import scan_payload
from tori_taurus.scanner.filters import DiscoveryFilters


@pytest.mark.parametrize(
    "values",
    [
        {"min_price": "0"},
        {"max_price": "6"},
        {"min_price": "2", "max_price": "1"},
        {"min_volume": "1.5"},
        {"min_volume": "1e1000000"},
        {"max_candidates": "200"},
        {"max_candidates": True},
        {"min_change_percent": "NaN"},
        {"min_change_percent": "-1"},
        {"unknown": 2},
    ],
)
def test_invalid_filters_fail_before_network(values):
    with pytest.raises(ValueError):
        scan_payload({"mode": "live", "provider": "webull", "filters": values})


def test_thresholds_and_exclusive_price_cap():
    f = DiscoveryFilters.from_payload(
        {
            "min_price": "1",
            "max_price": "3",
            "min_change_percent": "10",
            "min_volume": "200000",
            "max_candidates": "60",
        }
    )
    assert f.matches(Decimal(1), Decimal(10), 200000)
    assert not f.matches(Decimal(3), Decimal(10), 200000)
    assert not f.matches(Decimal(2), Decimal("9.9"), 200000)
    assert not f.matches(Decimal(2), Decimal(10), 199999)


def test_webull_depth_deduplicates_and_reports_remainder():
    tickers = [f"T{i}" for i in range(70)]

    def response(value):
        return SimpleNamespace(status_code=200, json=lambda: value)

    provider = WebullProvider(
        data=SimpleNamespace(
            screener=SimpleNamespace(
                list_most_active=lambda *a, **k: response([{"symbol": s} for s in tickers]),
                list_gainers_losers=lambda *a, **k: response([{"symbol": "T0"}]),
            ),
        ),
        account=SimpleNamespace(),
    )
    provider.snapshots = lambda symbols: [
        {"symbol": s, "price": "2", "pre_close": "1", "volume": "200000"} for s in symbols
    ]
    rows, coverage = provider.discover(DiscoveryFilters(max_candidates=60))
    assert len(rows) == 60 and len({r["symbol"] for r in rows}) == 60
    assert coverage["discovered"] == coverage["matched"] == 70
    assert coverage["not_inspected"] == 10
    assert coverage["filters"]["max_candidates"] == 60


def test_demo_filters_preserve_the_selected_symbols_observations():
    result = scan_payload({"mode": "demo", "filters": {"max_price": ".8"}})
    assert [r["symbol"] for r in result["candidates"]] == ["DEMOC"]
    assert result["candidates"][0]["report"]["symbol"] == "DEMOC"
    assert result["coverage"]["matched"] == 1


def test_adjusted_daily_volume_preserves_fractional_values_and_json_boundary():
    bars = [
        Bar(
            "TEST",
            datetime(2026, 10, day, tzinfo=UTC),
            1,
            1,
            1,
            1,
            Decimal(volume),
            "1d",
            "synthetic",
            volume_adjusted=True,
        )
        for day, volume in [(1, "10.25"), (2, "20.5")]
    ]
    assert bars[0].volume == Decimal("10.25")
    from tori_taurus.scanner import ScanConfig

    result = evaluate_daily(bars, as_of=bars[-1].timestamp, config=ScanConfig(volume_lookback=1))
    assert result["features"]["daily_relative_volume"] == "2"
    assert result["features"]["volume"] == "20.5"
    assert result["features"]["volume_basis"] == "adjusted"
    import json

    json.dumps(result)
    with pytest.raises(ValueError):
        Bar("TEST", bars[0].timestamp, 1, 1, 1, 1, Decimal("10.25"), "1d", "synthetic")
    with pytest.raises(ValueError):
        Bar(
            "TEST",
            bars[0].timestamp,
            1,
            1,
            1,
            1,
            Decimal("10.25"),
            "1m",
            "synthetic",
            volume_adjusted=True,
        )


def discovery_provider(listings, snapshots):
    def response(value):
        return SimpleNamespace(status_code=200, json=lambda: value)
    provider = WebullProvider(data=SimpleNamespace(screener=SimpleNamespace(
        list_most_active=lambda *a, **k: response(listings),
        list_gainers_losers=lambda *a, **k: response([]))), account=SimpleNamespace())
    provider.snapshots = lambda symbols: snapshots
    return provider


def test_discovery_skips_invalid_rows_and_reports_missing_coverage():
    p = discovery_provider([{"symbol": "GOOD"}, {"symbol": "BAD"}, None], [
        {"symbol": "BAD", "price": None},
        {"symbol": "GOOD", "price": "2", "pre_close": "1", "volume": "200000"},
        {"symbol": "GOOD", "price": "2", "pre_close": "1", "volume": "200000"}])
    rows, coverage = p.discover()
    assert len(rows) == 1 and rows[0]["symbol"] == "GOOD"
    assert coverage["invalid_listing_rows"] == 1
    assert coverage["invalid_snapshot_rows"] == 1
    assert coverage["missing_snapshots"] == 1
    assert coverage["discovered"] == 2


@pytest.mark.parametrize("listings,snapshots", [
    ({"unexpected": []}, []),
    ([None], []),
    ([{"symbol": "BAD"}], {"unexpected": []}),
    ([{"symbol": "BAD"}], []),
    ([{"symbol": "BAD"}], [{"symbol": "BAD", "price": "private-sentinel"}]),
])
def test_unusable_discovery_is_error_not_zero_matches(listings, snapshots):
    from tori_taurus.market_data import MarketDataError
    with pytest.raises(MarketDataError) as exc:
        discovery_provider(listings, snapshots).discover()
    assert "private-sentinel" not in str(exc.value)


def test_large_provider_lists_are_capped_before_snapshot_requests():
    def response(rows):
        return SimpleNamespace(status_code=200, json=lambda: rows)
    provider = WebullProvider(data=SimpleNamespace(screener=SimpleNamespace(
        list_most_active=lambda *a, **k: response([{"symbol": f"A{i}"} for i in range(500)]),
        list_gainers_losers=lambda *a, **k: response([{"symbol": f"G{i}"} for i in range(500)])
    )), account=SimpleNamespace())
    queried = []
    def snapshots(symbols):
        queried.extend(symbols)
        return [{"symbol": s, "price": "2", "pre_close": "1", "volume": "200000"}
                for s in symbols]
    provider.snapshots = snapshots
    rows, coverage = provider.discover()
    assert len(queried) == 400
    assert "A200" not in queried and "G200" not in queried
    assert coverage["listing_rows_returned"] == 1000
    assert coverage["listing_rows_considered"] == coverage["discovered"] == 400
    assert len(rows) == 20
