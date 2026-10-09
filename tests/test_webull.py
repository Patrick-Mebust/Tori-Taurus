"""Synthetic broker responses: validate privacy, account sizing and market provenance."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from tori_taurus.market_data import MarketDataError
from tori_taurus.market_data.webull import WebullProvider


def response(data, status=200):
    return SimpleNamespace(status_code=status, json=lambda: deepcopy(data))


@pytest.fixture
def broker(monkeypatch):
    monkeypatch.delenv("WEBULL_ACCOUNT_ID", raising=False)
    balance = {
        "total_asset_currency": "USD",
        "total_net_liquidation_value": "1000",
        "total_cash_balance": "20",
        "total_day_profit_loss": "-33",
        "account_currency_assets": [
            {"currency": "USD", "day_buying_power": "200", "overnight_buying_power": "20"}
        ],
    }
    holdings = [
        {
            "symbol": "TEST",
            "quantity": "10",
            "cost_price": "2.25",
            "currency": "USD",
            "instrument_type": "EQUITY",
            "market_value": "21",
            "unrealized_profit_loss": "-1.5",
        }
    ]
    account = SimpleNamespace(
        get_account_list=lambda: response([{"account_id": "PRIVATE-ID"}]),
        get_account_balance=lambda _: response(balance),
        get_account_position=lambda _: response(holdings),
    )
    return WebullProvider(data=SimpleNamespace(), account=account), balance, holdings


def test_account_preserves_cost_basis_and_conservative_buying_power(broker):
    provider, _, _ = broker
    result = provider.account_snapshot()
    assert result["equity"] == "1000" and result["buying_power"] == "20"
    assert result["holdings"][0]["average"] == "2.25"
    assert result["day_pnl"] == "-33" and "losses_today" not in result
    assert "PRIVATE-ID" not in str(result)


@pytest.mark.parametrize("quantity", ["1.5", "-10"])
def test_unsupported_positions_disable_sizing_without_rounding(broker, quantity):
    provider, _, holdings = broker
    holdings[0]["quantity"] = quantity
    result = provider.account_snapshot()
    assert result["sizing_issues"] and result["holdings"][0]["shares"] == quantity


def test_missing_buying_power_fails_closed(broker):
    provider, balance, _ = broker
    del balance["account_currency_assets"][0]["overnight_buying_power"]
    with pytest.raises(MarketDataError):
        provider.account_snapshot()


def test_sdk_errors_do_not_echo_secrets():
    def failure():
        raise RuntimeError("secret-token private-account")

    with pytest.raises(MarketDataError) as error:
        WebullProvider.call(failure)
    assert "secret-token" not in str(error.value)
    with pytest.raises(MarketDataError, match="entitlement"):
        WebullProvider.call(lambda: response({"secret": "private"}, 403))


def test_quote_preserves_exchange_timestamp(broker):
    provider, _, _ = broker
    provider.data.market_data = SimpleNamespace(
        get_snapshot=lambda *a, **k: response(
            [{"symbol": "TEST", "quote_time": 1791487440000, "bid": "2", "ask": "2.01"}]
        )
    )
    quote = provider.get_quote("TEST")
    assert quote.timestamp == datetime.fromtimestamp(1791487440, UTC)
    assert quote.mode == "live" and quote.source == "webull:openapi"


def test_bars_sort_and_reject_delay_or_duplicates(broker):
    provider, _, _ = broker
    start = datetime(2026, 10, 8, 14, tzinfo=UTC)
    rows = [
        {
            "time": (start + timedelta(minutes=i)).isoformat(),
            "open": "2",
            "high": "2.1",
            "low": "1.9",
            "close": "2",
            "volume": "100",
            "trading_session": "RTH",
        }
        for i in [1, 0]
    ]
    group = {"symbol": "TEST", "delay_minutes": 0, "result": rows}
    provider.data.market_data = SimpleNamespace(
        get_batch_history_bar=lambda *a, **k: response({"result": [group]})
    )
    bars = provider.get_bars("TEST", start, start + timedelta(minutes=2), "1m")
    assert [b.timestamp for b in bars] == [start, start + timedelta(minutes=1)]
    group["delay_minutes"] = 15
    with pytest.raises(MarketDataError):
        provider.get_bars("TEST", start, start + timedelta(minutes=2), "1m")
    group["delay_minutes"] = 0
    rows.append(rows[0])
    with pytest.raises(MarketDataError):
        provider.get_bars("TEST", start, start + timedelta(minutes=2), "1m")


def test_webull_adjusted_daily_volume_is_not_rounded(broker):
    provider, _, _ = broker
    start = datetime(2026, 10, 8, tzinfo=UTC)
    row = {
        "time": start.isoformat(),
        "open": "2",
        "high": "2.1",
        "low": "1.9",
        "close": "2",
        "volume": "49894.2",
        "trading_session": "RTH",
    }
    group = {"symbol": "TEST", "delay_minutes": 0, "result": [row]}
    provider.data.market_data = SimpleNamespace(
        get_batch_history_bar=lambda *a, **k: response({"result": [group]})
    )
    (bar,) = provider.get_bars("TEST", start, start + timedelta(days=1), "1d")
    assert str(bar.volume) == "49894.2" and bar.volume_adjusted
    with pytest.raises(MarketDataError):
        provider.get_bars("TEST", start, start + timedelta(minutes=2), "1m")


def test_real_sdk_constructor_accepts_verification_timeout(monkeypatch):
    sdk = pytest.importorskip("webull.data.data_client")
    monkeypatch.setenv("WEBULL_APP_KEY", "synthetic-key")
    monkeypatch.setenv("WEBULL_APP_SECRET", "synthetic-secret")
    monkeypatch.delenv("WEBULL_ACCESS_TOKEN", raising=False)
    clients = []
    monkeypatch.setattr(sdk, "DataClient", lambda client: clients.append(client))
    WebullProvider()
    assert clients[0].get_token_check_duration_seconds() == 30


@pytest.mark.parametrize(
    "status, expected",
    [(403, "subscription"), (401, "Authentication"), (429, "rate limit"), (417, "HTTP 417")],
)
def test_sdk_server_errors_report_stage_without_private_message(status, expected):
    class BrokerError(Exception):
        http_status = status

    def list_most_active():
        raise BrokerError("private-token private-account")

    with pytest.raises(MarketDataError) as caught:
        WebullProvider.call(list_most_active)
    message = str(caught.value)
    assert expected in message and "most-active stock discovery" in message
    assert "private-token" not in message and "private-account" not in message
