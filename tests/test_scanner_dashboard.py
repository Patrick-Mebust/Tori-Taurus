"""Candidate discovery, derived levels and account-aware scenarios."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tori_taurus.market_data import MarketDataError
from tori_taurus.report import build_report
from tori_taurus.scanner.dashboard import demo_observations, derive_plan, scan_payload
from tori_taurus.scanner.discovery import discover


def report():
    clock, quote, daily, bars = demo_observations("TEST")
    return build_report("TEST", as_of=clock, quote=quote, daily_bars=daily, session_bars=bars)


def test_demo_discovers_distinct_scenarios_without_ticker_input():
    data = scan_payload({"mode": "demo"})
    assert len(data["candidates"]) == 4 and not data["errors"]
    states = {row["plan"]["state"] for row in data["candidates"]}
    assert {"SETUP CONFIRMED", "WATCH", "NO VALID SETUP"} <= states
    assert all(row["quote"]["mode"] == "replay" for row in data["candidates"])
    assert not data["ready_to_trade"] and not data["account_configured"]


def test_webull_scan_reaches_quote_and_bars_with_broker_holdings():
    clock, quote, daily, bars = demo_observations("TEST")
    calls = []

    class Provider:
        feed = "webull"

        def account_snapshot(self):
            return {
                "equity": "1000",
                "buying_power": "20",
                "holdings": [{"symbol": "TEST", "shares": "10", "average": "1.90"}],
                "sizing_issues": [],
            }

        def discover(self):
            return [{"symbol": "TEST", "change_percent": "5", "volume": 250000}], {
                "inspected": 1,
                "not_inspected": 0,
            }

        def get_quote(self, ticker):
            calls.append("quote")
            return quote

        def get_bars(self, ticker, start, end, interval):
            calls.append(interval)
            return daily if interval == "1d" else bars

    class Calendar:
        def classify(self, timestamp):
            return "regular"

        def _bounds(self, day):
            from datetime import timedelta

            return (
                clock,
                bars[0].timestamp,
                clock + timedelta(hours=4),
                clock + timedelta(hours=8),
            )

    result = scan_payload(
        {
            "mode": "live",
            "provider": "webull",
            "account": {"equity": "99999", "buying_power": "99999"},
            "holdings": [{"symbol": "TEST", "shares": "99", "average": "9"}],
        },
        now=clock,
        provider=Provider(),
        sessions=Calendar(),
    )
    assert calls == ["quote", "1d", "1m"]
    assert not result["errors"] and len(result["candidates"]) == 1
    assert result["broker_account"]["buying_power"] == "20"
    assert result["candidates"][0]["plan"]["holding"] == {"shares": "10", "average": "1.90"}
    assert result["candidates"][0]["plan"]["risk"] is None


def test_prices_are_derived_from_observed_levels_and_rounded():
    source = report()
    plan = derive_plan(source, demo=True)
    setup = source["setups"][plan["setup"]]
    assert Decimal(plan["entry"]) > Decimal(setup["confirmation_level"])
    assert Decimal(plan["entry"]) >= Decimal(source["quote"]["ask"])
    assert Decimal(plan["stop"]) < Decimal(setup["invalidation_level"])
    assert Decimal(plan["target_2r"]) == Decimal(plan["entry"]) + 2 * (
        Decimal(plan["entry"]) - Decimal(plan["stop"])
    )
    assert plan["risk"] is None


def test_account_limits_drive_shares_and_loss_not_fixed_defaults():
    plan = derive_plan(report(), demo=True, account={"equity": "1000", "buying_power": "100"})
    risk = plan["risk"]
    assert risk["requested_add_shares"] > 0
    assert Decimal(risk["add_cost"]) <= 100
    assert Decimal(risk["conservative_budget_loss"]) <= 10
    assert Decimal(risk["combined_average"]) == Decimal(plan["entry"])


def test_existing_holdings_drive_projected_average_and_risk():
    plan = derive_plan(
        report(),
        demo=True,
        account={"equity": "1000", "buying_power": "100"},
        holding={"shares": "10", "average": "1.90"},
    )
    r = plan["risk"]
    n = r["requested_add_shares"]
    assert Decimal(r["combined_average"]) == (Decimal(19) + n * Decimal(plan["entry"])) / (10 + n)
    assert r["existing_shares"] == 10 and plan["holding"]["average"] == "1.90"


def test_averaging_down_is_blocked_without_fabricated_thesis():
    plan = derive_plan(
        report(),
        demo=True,
        account={"equity": "1000", "buying_power": "100"},
        holding={"shares": "10", "average": "2.50"},
    )
    assert plan["risk"]["requested_add_shares"] == 0
    assert plan["state"] == "RISK BLOCKED"
    assert "unsupported_averaging_down" in plan["guardrails"]["blockers"]


def test_daily_loss_limit_prevents_candidate_allocation():
    plan = derive_plan(
        report(),
        demo=True,
        account={"equity": "1000", "buying_power": "100"},
        context={"losses_today": "30"},
    )
    assert plan["risk"]["requested_add_shares"] == 0
    assert plan["state"] == "RISK BLOCKED"


def test_stale_or_closed_quote_never_produces_live_levels():
    source = report()
    assert derive_plan(source)["entry"] is None
    source["quote"]["fresh"] = True
    source["quote"]["session"] = "postmarket"
    assert derive_plan(source)["state"] == "DATA UNAVAILABLE"


def test_wide_spread_and_invalid_setup_do_not_invent_prices():
    source = report()
    source["quote"]["bid"] = "1"
    assert derive_plan(source, demo=True)["state"] == "SPREAD TOO WIDE"
    source = report()
    for s in source["setups"].values():
        s["state"] = "INVALIDATED"
    assert derive_plan(source, demo=True)["entry"] is None


def test_missing_credentials_do_not_substitute_demo_for_live(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
    with pytest.raises(MarketDataError):
        scan_payload({"mode": "live"})


def test_duplicate_holdings_are_rejected():
    with pytest.raises(ValueError):
        scan_payload({"holdings": [{"symbol": "TEST", "shares": "1", "average": "2"}] * 2})


class Provider:
    feed = "iex"

    def _get_json(self, url):
        key = "most_actives" if "most-actives" in url else "gainers"
        return {
            "last_updated": datetime.now(UTC).isoformat(),
            key: [{"symbol": s} for s in ["GOOD", "HIGH", "FALL", "MISSING"]],
        }

    def _request(self, path, params):
        assert path == "snapshots" and params["feed"] == "iex"
        now = datetime.now(UTC).isoformat()
        return {
            s: {
                "latestTrade": {"p": p, "t": now},
                "prevDailyBar": {"c": "2"},
                "dailyBar": {"v": 200000},
            }
            for s, p in [("GOOD", "2.2"), ("HIGH", "5"), ("FALL", "1.8")]
        }


def test_discovery_deduplicates_and_filters_price_momentum_missing_data():
    rows, coverage = discover(Provider())
    assert [r["symbol"] for r in rows] == ["GOOD"]
    assert coverage["discovered"] == 4 and coverage["matched"] == 1
    assert len(coverage["filtered"]) == 3
    assert coverage["analysis_feed"] == "iex"


def test_discovery_rejects_malformed_top_level(monkeypatch):
    provider = Provider()
    monkeypatch.setattr(provider, "_get_json", lambda url: {})
    with pytest.raises(MarketDataError):
        discover(provider)
