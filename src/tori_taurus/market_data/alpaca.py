"""Read-only Alpaca REST adapter with explicit feed provenance."""

import json
import math
from datetime import datetime
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import Bar, Quote, symbol, utc

TIMEFRAMES = {"1m": "1Min", "5m": "5Min", "15m": "15Min", "1h": "1Hour", "1d": "1Day"}


class MarketDataError(RuntimeError):
    """Sanitized failure without response bodies or credentials."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AlpacaProvider:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        feed: str = "iex",
        timeout: float = 10,
        max_pages: int = 100,
    ):
        if not api_key.strip() or not api_secret.strip():
            raise ValueError("Alpaca credentials are required")
        if feed not in {"iex", "sip"}:
            raise ValueError("Supported feeds: iex, sip")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be positive and finite")
        if type(max_pages) is not int or max_pages <= 0:
            raise ValueError("Page limit must be a positive integer")
        self._headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}
        self.feed, self.timeout, self.max_pages = feed, timeout, max_pages
        self._opener = build_opener(_NoRedirect())

    def _request(self, path: str, params: dict) -> dict:
        url = "https://data.alpaca.markets/v2/stocks/" + path + "?" + urlencode(params)
        return self._get_json(url)

    def _get_json(self, url: str) -> dict:
        request = Request(url, headers=self._headers)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read(), parse_float=Decimal)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise MarketDataError(f"Alpaca HTTP {status}") from None
        except (URLError, OSError, ValueError):
            raise MarketDataError("Alpaca transport or JSON failure") from None
        if not isinstance(payload, dict):
            raise MarketDataError("Invalid Alpaca response") from None
        return payload

    def get_quote(self, ticker: str) -> Quote:
        ticker = symbol(ticker)
        payload = self._request(ticker + "/quotes/latest", {"feed": self.feed})
        try:
            if payload.get("symbol") != ticker:
                raise ValueError("Symbol mismatch")
            q = payload["quote"]
            return Quote(
                ticker,
                datetime.fromisoformat(q["t"]),
                q["bp"],
                q["ap"],
                source="alpaca:" + self.feed,
                mode="live",
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise MarketDataError("Invalid Alpaca quote") from None

    def get_bars(
        self, ticker: str, start: datetime, end: datetime, interval: str = "1d"
    ) -> list[Bar]:
        ticker, start, end = symbol(ticker), utc(start), utc(end)
        if start >= end or interval not in TIMEFRAMES:
            raise ValueError("Invalid range or interval")
        params = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timeframe": TIMEFRAMES[interval],
            "feed": self.feed,
            "adjustment": "raw",
            "sort": "asc",
            "limit": 10000,
            "asof": "-",
        }
        records, timestamps, tokens = [], set(), set()
        for _ in range(self.max_pages):
            payload = self._request(ticker + "/bars", params)
            try:
                if payload.get("symbol") != ticker or not isinstance(payload["bars"], list):
                    raise ValueError("Invalid bar collection")
                for b in payload["bars"]:
                    bar = Bar(
                        ticker,
                        datetime.fromisoformat(b["t"]),
                        b["o"],
                        b["h"],
                        b["l"],
                        b["c"],
                        b["v"],
                        interval,
                        source="alpaca:" + self.feed,
                        mode="replay",
                    )
                    if bar.timestamp in timestamps:
                        raise ValueError("Duplicate bar")
                    timestamps.add(bar.timestamp)
                    if start <= bar.timestamp < end:
                        records.append(bar)
                token = payload.get("next_page_token")
                if token is not None and (not isinstance(token, str) or not token):
                    raise ValueError("Invalid page token")
            except (KeyError, TypeError, ValueError, ArithmeticError):
                raise MarketDataError("Invalid Alpaca bars") from None
            if token is None:
                return sorted(records, key=lambda b: b.timestamp)
            if token in tokens:
                raise MarketDataError("Repeated Alpaca page token")
            tokens.add(token)
            params["page_token"] = token
        raise MarketDataError("Alpaca pagination limit reached; incomplete results rejected")
