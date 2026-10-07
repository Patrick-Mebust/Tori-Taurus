"""Explicit read-only live check. Output contains market fields, never credentials."""

import argparse
import json
import math
import os
from datetime import UTC, datetime, timedelta

from .alpaca import AlpacaProvider, MarketDataError
from .models import symbol, utc
from .provider import MarketDataProvider, validate_freshness
from .sessions import NyseSessions, SessionProvider


def check_market_data(
    provider: MarketDataProvider,
    ticker: str,
    *,
    now: datetime | None = None,
    max_age: timedelta = timedelta(seconds=60),
    history_days: int = 7,
) -> dict:
    """Validate a live quote and nonempty daily history against an explicit clock."""
    ticker = symbol(ticker)
    if max_age < timedelta(0) or type(history_days) is not int or not 1 <= history_days <= 30:
        raise ValueError("Invalid smoke-check range or freshness budget")
    quote = provider.get_quote(ticker)
    now = utc(now) if now is not None else datetime.now(UTC)
    if quote.symbol != ticker:
        raise MarketDataError("Quote symbol mismatch")
    try:
        validate_freshness(quote, now=now, max_age=max_age)
        fresh = True
    except ValueError:
        fresh = False
    start = now - timedelta(days=history_days)
    bars = provider.get_bars(ticker, start, now, interval="1d")
    if not bars:
        raise MarketDataError("No historical bars returned")
    if any(
        b.symbol != ticker
        or b.interval != "1d"
        or not start <= b.timestamp < now
        or b.source != quote.source
        for b in bars
    ):
        raise MarketDataError("Historical record identity or range mismatch")
    times = [b.timestamp for b in bars]
    if times != sorted(set(times)):
        raise MarketDataError("History is unordered or duplicated")
    return {
        "status": "passed" if fresh else "failed",
        "live_verified": fresh,
        "checked_at": now.isoformat(),
        "symbol": ticker,
        "quote": {
            "timestamp": quote.timestamp.isoformat(),
            "source": quote.source,
            "mode": quote.mode,
            "session": quote.session,
            "bid": str(quote.bid),
            "ask": str(quote.ask),
            "fresh": fresh,
            "age_seconds": (now - quote.timestamp).total_seconds(),
        },
        "history": {
            "count": len(bars),
            "interval": "1d",
            "start": start.isoformat(),
            "end_exclusive": now.isoformat(),
            "first_timestamp": times[0].isoformat(),
            "last_timestamp": times[-1].isoformat(),
        },
        "note": "Read-only data check; no order was submitted."
        if fresh
        else "Quote is stale, future-dated, delayed, or replay; live check failed.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Alpaca quote/history smoke check")
    parser.add_argument("ticker", nargs="?", default="AAPL")
    parser.add_argument("--feed", choices=("iex", "sip"), default="iex")
    parser.add_argument("--max-age-seconds", type=float, default=60)
    parser.add_argument("--history-days", type=int, default=7)
    parser.add_argument("--sessions", action="store_true", help="Enable optional NYSE calendar")
    args = parser.parse_args(argv)
    try:
        ticker = symbol(args.ticker)
        if (
            not math.isfinite(args.max_age_seconds)
            or args.max_age_seconds < 0
            or not 1 <= args.history_days <= 30
        ):
            raise ValueError("Invalid arguments")
        key, secret = os.environ.get("ALPACA_API_KEY", ""), os.environ.get("ALPACA_API_SECRET", "")
        if not key.strip() or not secret.strip():
            print(
                json.dumps(
                    {
                        "status": "not_run",
                        "live_verified": False,
                        "reason": "Configure ALPACA_API_KEY and ALPACA_API_SECRET locally.",
                    }
                )
            )
            return 2
        provider = AlpacaProvider(key, secret, feed=args.feed)
        if args.sessions:
            provider = SessionProvider(provider, NyseSessions())
        report = check_market_data(
            provider,
            ticker,
            max_age=timedelta(seconds=args.max_age_seconds),
            history_days=args.history_days,
        )
        print(json.dumps(report))
        return 0 if report["live_verified"] else 1
    except MarketDataError as exc:
        print(json.dumps({"status": "failed", "live_verified": False, "reason": str(exc)}))
        return 1
    except (ValueError, RuntimeError, OverflowError):
        print(
            json.dumps(
                {
                    "status": "not_run",
                    "live_verified": False,
                    "reason": "Invalid configuration or missing calendar extra.",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
