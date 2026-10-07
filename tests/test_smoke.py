"""Offline smoke-check acceptance tests with synthetic provider data."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from tori_taurus.market_data import Bar, MarketDataError, Quote
from tori_taurus.market_data.smoke import check_market_data, main

NOW = datetime(2026, 10, 7, 15, tzinfo=UTC)


class Provider:
    def __init__(self, *, mode="live", age=0):
        self.quote = Quote("AAPL", NOW - timedelta(seconds=age), 1, 2, "synthetic", mode=mode)
        self.bars = [Bar("AAPL", NOW - timedelta(days=1), 1, 2, 0, 1, 10, "1d", "synthetic")]

    def get_quote(self, ticker):
        return self.quote

    def get_bars(self, ticker, start, end, interval="1d"):
        return self.bars


def test_success():
    report = check_market_data(Provider(), "aapl", now=NOW)
    assert report["status"] == "passed" and report["live_verified"]
    assert report["history"]["count"] == 1
    assert report["quote"]["bid"] == "1"
    assert report["checked_at"] == NOW.isoformat()


@pytest.mark.parametrize(
    "options", [{"mode": "replay"}, {"mode": "delayed"}, {"age": 61}, {"age": -1}]
)
def test_noncurrent_data_fails(options):
    report = check_market_data(Provider(**options), "AAPL", now=NOW)
    assert report["status"] == "failed" and not report["live_verified"]


@pytest.mark.parametrize("case", ["empty", "duplicate", "wrong_symbol", "wrong_source", "future"])
def test_bad_history(case):
    provider = Provider()
    if case == "empty":
        provider.bars = []
    elif case == "duplicate":
        provider.bars *= 2
    else:
        provider.bars = [
            Bar(
                "MSFT" if case == "wrong_symbol" else "AAPL",
                NOW if case == "future" else NOW - timedelta(days=1),
                1,
                2,
                0,
                1,
                10,
                "1d",
                "other" if case == "wrong_source" else "synthetic",
            )
        ]
    with pytest.raises(MarketDataError):
        check_market_data(provider, "AAPL", now=NOW)


def test_cli_missing_configuration(monkeypatch, capsys):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
    assert main([]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "not_run"


@pytest.mark.parametrize(
    "args",
    [
        ["--max-age-seconds", "nan"],
        ["--history-days", "0"],
        ["../bad"],
        ["--max-age-seconds", "-1"],
    ],
)
def test_cli_invalid_configuration(args, capsys):
    assert main(args) == 2
    assert not json.loads(capsys.readouterr().out)["live_verified"]


def test_cli_success_without_network(monkeypatch, capsys):
    from tori_taurus.market_data import smoke

    monkeypatch.setenv("ALPACA_API_KEY", "synthetic-key")
    monkeypatch.setenv("ALPACA_API_SECRET", "synthetic-secret")
    monkeypatch.setattr(smoke, "AlpacaProvider", lambda *a, **kw: Provider())
    original = smoke.check_market_data
    monkeypatch.setattr(
        smoke, "check_market_data", lambda p, ticker, **kw: original(p, ticker, now=NOW, **kw)
    )
    assert main([]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["live_verified"]
    assert "synthetic-secret" not in output and "synthetic-key" not in output
