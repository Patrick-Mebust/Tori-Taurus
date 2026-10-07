"""Synthetic API responses; no credentials or network access required."""

import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.error import HTTPError, URLError

import pytest

from tori_taurus.market_data import validate_freshness
from tori_taurus.market_data.alpaca import AlpacaProvider, MarketDataError, _NoRedirect

NOW = datetime(2026, 10, 7, 15, tzinfo=UTC)


def provider(monkeypatch, pages, **options):
    client = AlpacaProvider("synthetic-key", "synthetic-secret", **options)
    calls = []
    responses = iter(pages)

    def request(path, params):
        calls.append((path, dict(params)))
        return next(responses)

    monkeypatch.setattr(client, "_request", request)
    return client, calls


def quote_payload(**changes):
    return {
        "symbol": "AAPL",
        "quote": {"t": NOW.isoformat(), "bp": "1.123456789", "ap": "1.2"} | changes,
    }


def bar(minute=0):
    return {
        "t": (NOW + timedelta(minutes=minute)).isoformat(),
        "o": 1,
        "h": 2,
        "l": 0,
        "c": 1,
        "v": 10,
    }


def test_quote_and_feed(monkeypatch):
    client, calls = provider(monkeypatch, [quote_payload()], feed="sip")
    q = client.get_quote(" aapl ")
    assert q.bid == Decimal("1.123456789")
    assert q.source == "alpaca:sip" and q.mode == "live" and q.session == "unknown"
    validate_freshness(q, now=NOW, max_age=timedelta(seconds=1))
    assert calls == [("AAPL/quotes/latest", {"feed": "sip"})]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"symbol": "MSFT", "quote": {}},
        quote_payload(bp="NaN"),
        quote_payload(t="bad"),
        quote_payload(bp=3),
        {"symbol": "AAPL", "quote": None},
    ],
)
def test_invalid_quotes(monkeypatch, payload):
    client, _ = provider(monkeypatch, [payload])
    with pytest.raises(MarketDataError, match="Invalid Alpaca quote"):
        client.get_quote("AAPL")


def test_paginated_bars_and_exclusive_end(monkeypatch):
    client, calls = provider(
        monkeypatch,
        [
            {"symbol": "AAPL", "bars": [bar(1)], "next_page_token": "page2"},
            {"symbol": "AAPL", "bars": [bar(0), bar(2)], "next_page_token": None},
        ],
    )
    records = client.get_bars("AAPL", NOW, NOW + timedelta(minutes=2), "1m")
    assert [b.timestamp for b in records] == [NOW, NOW + timedelta(minutes=1)]
    assert all(b.mode == "replay" for b in records)
    assert calls[0][1]["timeframe"] == "1Min"
    assert calls[0][1]["adjustment"] == "raw"
    assert calls[1][1]["page_token"] == "page2"


@pytest.mark.parametrize(
    "pages,options",
    [
        ([{"symbol": "AAPL", "bars": [bar(), bar()]}], {}),
        ([{"symbol": "MSFT", "bars": []}], {}),
        ([{"symbol": "AAPL", "bars": [bar() | {"v": 1.5}]}], {}),
        ([{"symbol": "AAPL", "bars": [], "next_page_token": "same"}] * 2, {}),
        ([{"symbol": "AAPL", "bars": [], "next_page_token": "more"}], {"max_pages": 1}),
        ([{"symbol": "AAPL", "bars": [], "next_page_token": 12}], {}),
    ],
)
def test_invalid_or_incomplete_bars(monkeypatch, pages, options):
    client, _ = provider(monkeypatch, pages, **options)
    with pytest.raises(MarketDataError):
        client.get_bars("AAPL", NOW, NOW + timedelta(days=1))


class FakeOpener:
    def __init__(self, result):
        self.result = result
        self.request = None

    def open(self, request, *, timeout):
        self.request = request
        if isinstance(self.result, Exception):
            raise self.result
        return io.BytesIO(self.result)


def test_transport_decimal_and_origin():
    client = AlpacaProvider("synthetic-key", "synthetic-secret")
    fake = FakeOpener(b'{"price": 1.123456789}')
    client._opener = fake
    assert client._request("AAPL/quotes/latest", {"feed": "iex"})["price"] == Decimal("1.123456789")
    assert (
        fake.request.full_url == "https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest?feed=iex"
    )
    assert _NoRedirect().redirect_request(None, None, 302, None, None, "https://other") is None


@pytest.mark.parametrize(
    "result",
    [
        URLError("synthetic-secret"),
        TimeoutError("synthetic-key"),
        b"invalid",
        b"[]",
        HTTPError("https://example", 401, "synthetic-secret", {}, None),
        HTTPError("https://example", 429, "synthetic-secret", {}, None),
    ],
)
def test_transport_errors_are_sanitized(result):
    client = AlpacaProvider("synthetic-key", "synthetic-secret")
    client._opener = FakeOpener(result)
    with pytest.raises(MarketDataError) as error:
        client._request("AAPL/quotes/latest", {})
    assert "synthetic-secret" not in str(error.value)
    assert "synthetic-key" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize(
    "options",
    [
        {"feed": "delayed_sip"},
        {"timeout": 0},
        {"timeout": float("nan")},
        {"max_pages": 0},
        {"max_pages": True},
    ],
)
def test_configuration(options):
    with pytest.raises(ValueError):
        AlpacaProvider("synthetic-key", "synthetic-secret", **options)


def test_missing_credentials():
    with pytest.raises(ValueError):
        AlpacaProvider("", "")


def test_empty_and_invalid_requests(monkeypatch):
    client, calls = provider(monkeypatch, [{"symbol": "AAPL", "bars": []}])
    assert client.get_bars("AAPL", NOW, NOW + timedelta(days=1)) == []
    with pytest.raises(ValueError):
        client.get_bars("AAPL", NOW, NOW)
    with pytest.raises(ValueError):
        client.get_bars("AAPL", NOW, NOW + timedelta(days=1), "bad")
    with pytest.raises(ValueError):
        client.get_quote("../bad")
    assert len(calls) == 1
