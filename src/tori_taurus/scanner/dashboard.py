"""Discover candidates and derive transparent conditional plans from setup levels."""

import os
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from threading import Lock

from tori_taurus.behavior.guardrails import evaluate_guardrails
from tori_taurus.market_data import (
    AlpacaProvider,
    Bar,
    MarketDataError,
    NyseSessions,
    Quote,
    SessionProvider,
)
from tori_taurus.report import build_report
from tori_taurus.risk import evaluate_risk

from .discovery import discover
from .filters import DiscoveryFilters


def derive_plan(report, *, account=None, holding=None, context=None, demo=False, now=None):
    """Prices require valid observed levels; position estimates require account inputs."""
    from tori_taurus.beta import parse_inputs

    now = now or datetime.now(UTC)
    quote = report["quote"]
    base = {
        "entry": None,
        "stop": None,
        "target_2r": None,
        "risk": None,
        "guardrails": None,
        "holding": holding,
        "setup": None,
        "state": "NO VALID SETUP",
        "reason": "No eligible setup with both confirmation and invalidation levels.",
        "basis": "Proposed conditional prices; no orders or verified broker stops.",
    }
    if not demo and (not quote.get("fresh") or quote.get("session") != "regular"):
        return base | {
            "state": "DATA UNAVAILABLE",
            "reason": "A fresh regular-session quote is required.",
        }
    eligible = [
        (name, item)
        for name, item in report["setups"].items()
        if item["state"] in {"CONFIRMED", "WATCH"}
        and item.get("confirmation_level") is not None
        and item.get("invalidation_level") is not None
    ]
    eligible.sort(key=lambda pair: (pair[1]["state"] != "CONFIRMED", pair[0]))
    if not eligible:
        return base
    name, setup = eligible[0]
    level, anchor = Decimal(setup["confirmation_level"]), Decimal(setup["invalidation_level"])
    ask, bid = Decimal(quote["ask"]), Decimal(quote["bid"])
    if bid <= 0 or ask <= 0 or (ask - bid) / ask * 100 > 2:
        return base | {
            "state": "SPREAD TOO WIDE",
            "reason": "A valid two-sided quote with at most 2% spread is required.",
        }
    # Decimal display increments are planning buffers, not exchange tick-size certification.
    tick = Decimal(".0001") if level < 1 else Decimal(".01")
    entry = max(ask, (level / tick).to_integral_value(rounding=ROUND_CEILING) * tick + tick)
    entry = (entry / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    stop = (anchor / tick).to_integral_value(rounding=ROUND_FLOOR) * tick - tick
    if not 0 < stop < entry < 5:
        return base | {
            "reason": "Derived stop/entry does not satisfy the under-$5 long-plan bounds."
        }
    base |= {
        "entry": str(entry),
        "stop": str(stop),
        "target_2r": str(entry + 2 * (entry - stop)),
        "setup": name,
        "state": "SETUP CONFIRMED" if setup["state"] == "CONFIRMED" else "WATCH",
        "reason": setup["reason"],
        "entry_basis": "Greater of current ask and confirmation level plus one planning increment.",
        "stop_basis": "Observed invalidation level minus one planning increment.",
        "target_basis": "Illustrative 2R arithmetic; not a predicted price or resistance target.",
    }
    if not account:
        base["sizing_reason"] = (
            "Set account equity and buying power once to calculate shares, average cost and dollar risk."
        )
        return base
    values = dict(account) | {
        "entry": str(entry),
        "stop": str(stop),
        "requested_shares": "1",
        "existing_shares": (holding or {}).get("shares", "0"),
        "existing_average": (holding or {}).get("average", "0"),
    }
    reference = report["intraday"].get("last_close")
    reference = Decimal(reference) if reference else ask
    plan, rails = parse_inputs(
        {"plan": values, "guardrails": context or {}}, report["symbol"], reference
    )
    guards = evaluate_guardrails(plan, rails, as_of=now)
    shares = guards["allowable_add_shares_after_guardrails"]
    plan = replace(plan, requested_shares=shares)
    base["risk"] = evaluate_risk(plan)
    # Preserve blockers from the one-share probe; zero sizing must not erase an averaging-down flag.
    base["guardrails"] = guards
    if shares == 0:
        base["state"] = "RISK BLOCKED"
    base["sizing_reason"] = (
        "Each candidate is a separate scenario using the same buying power; do not combine allocations."
    )
    return base


def demo_observations(ticker, scale=1, kind="confirmed"):
    start = datetime(2026, 10, 7, 14, tzinfo=UTC)
    # Initial rising impulse, a shallow first pullback and a later confirmation.
    closes = (
        ["2.00", "2.06", "2.12", "2.10", "2.14"]
        if kind != "none"
        else ["2.14", "2.13", "2.12", "2.11", "2.10"]
    )
    if kind == "watch":
        closes = ["2.00", "1.96", "2.01"]
    multiplier = Decimal(str(scale))
    bars = [
        Bar(
            ticker,
            start + timedelta(minutes=i),
            Decimal(c) * multiplier,
            (Decimal(c) + Decimal(".01")) * multiplier,
            (Decimal(c) - Decimal(".01")) * multiplier,
            Decimal(c) * multiplier,
            50000 + i * 5000,
            "1m",
            "synthetic:scanner",
            session="regular",
        )
        for i, c in enumerate(closes)
    ]
    clock = bars[-1].timestamp + timedelta(minutes=1)
    quote = Quote(
        ticker,
        clock,
        bars[-1].close - Decimal(".001"),
        bars[-1].close + Decimal(".001"),
        "synthetic:scanner",
        session="regular",
    )
    daily = [
        Bar(
            ticker,
            start - timedelta(days=25 - i),
            Decimal("1.8") * multiplier,
            Decimal("2.2") * multiplier,
            Decimal("1.7") * multiplier,
            Decimal("1.9") * multiplier,
            150000 + i * 1000,
            "1d",
            "synthetic:scanner",
        )
        for i in range(25)
    ]
    return clock, quote, daily, bars


_LIVE_SCAN_LOCK = Lock()


def scan_payload(payload, *, now=None, provider=None, sessions=None):
    live = isinstance(payload, dict) and payload.get("mode") == "live"
    if live and not _LIVE_SCAN_LOCK.acquire(blocking=False):
        raise MarketDataError(
            "A live scan is already running. Wait for it to finish before scanning again."
        )
    try:
        return _scan_payload(payload, now=now, provider=provider, sessions=sessions)
    finally:
        if live:
            _LIVE_SCAN_LOCK.release()


def _scan_payload(payload, *, now=None, provider=None, sessions=None):
    from tori_taurus.beta import _integer, credentials_available, fetch_live_data, parse_inputs
    from tori_taurus.market_data.models import symbol

    if not isinstance(payload, dict):
        raise TypeError("Scan request must be an object")
    now = now or datetime.now(UTC)
    mode = payload.get("mode", "demo")
    if mode not in {"demo", "live"}:
        raise ValueError("Invalid scan mode")
    filters = DiscoveryFilters.from_payload(payload.get("filters"))
    broker = None
    if mode == "live" and payload.get("provider") == "webull":
        from tori_taurus.market_data.webull import WebullProvider

        provider = provider or WebullProvider()
        broker = provider.account_snapshot()
        payload = dict(payload)
        limits = payload.get("account") or {}
        payload["account"] = {
            "equity": broker["equity"],
            "buying_power": broker["buying_power"],
            "risk_budget_percent": limits.get("risk_budget_percent", "1"),
            "max_concentration_percent": limits.get("max_concentration_percent", "20"),
        }
        payload["holdings"] = broker["holdings"] if not broker["sizing_issues"] else []
        if broker["sizing_issues"] or Decimal(broker["equity"]) <= 0:
            payload["account"] = None
    account = payload.get("account") or None
    context = payload.get("guardrails") or {}
    holdings = payload.get("holdings", [])
    if not isinstance(holdings, list) or len(holdings) > 100:
        raise ValueError("At most 100 holdings")
    positions = {}
    for row in holdings:
        ticker = symbol(row["symbol"])
        if ticker in positions:
            raise ValueError("Duplicate holding")
        positions[ticker] = {"shares": str(_integer(row["shares"])), "average": row["average"]}
        parse_inputs(
            {
                "plan": (account or {})
                | {"existing_shares": row["shares"], "existing_average": row["average"]}
            },
            ticker,
            None,
        )
    if account:
        parse_inputs({"plan": account, "guardrails": context}, "TEST", None)
    rows, errors = [], []
    if mode == "demo":
        specs = [
            ("DEMOA", 1, "confirmed"),
            ("DEMOB", "1.5", "watch"),
            ("DEMOC", ".3", "confirmed"),
            ("DEMOD", "1.8", "none"),
        ]
        candidates = [
            {
                "symbol": s,
                "last": str(
                    Decimal("2.01" if kind == "watch" else "2.10" if kind == "none" else "2.14")
                    * Decimal(str(scale))
                ),
                "change_percent": str(8 - i),
                "volume": 250000 - i * 20000,
            }
            for i, (s, scale, kind) in enumerate(specs)
        ]
        candidates = [
            c for c in candidates
            if filters.matches(Decimal(c["last"]), Decimal(c["change_percent"]), c["volume"])
        ]
        demo_specs = {s: (s, scale, kind) for s, scale, kind in specs}
        coverage = {
            "universe": "Four fabricated scenarios, not real stocks",
            "discovered": 4,
            "matched": len(candidates),
            "inspected": len(candidates),
            "not_inspected": 0,
            "analysis_feed": "synthetic",
            "filters": filters.as_dict(),
            "limits": "Synthetic prices and volume; no live discovery.",
        }
    else:
        if provider is None:
            if not credentials_available():
                raise MarketDataError(
                    "Live scanning needs locally configured Alpaca credentials. Demo results are fabricated."
                )
            provider = AlpacaProvider(
                os.environ["ALPACA_API_KEY"],
                os.environ["ALPACA_API_SECRET"],
                feed=payload.get("feed", "iex"),
                max_pages=3,
            )
        candidates, coverage = (
            provider.discover(filters) if broker else discover(provider, filters)
        )
        sessions = sessions or NyseSessions()
        labeled = SessionProvider(provider, sessions)
    started = time.monotonic()
    for index, candidate in enumerate(candidates):
        if mode == "live" and time.monotonic() - started > 90:
            coverage["not_inspected"] += len(candidates) - index
            coverage["inspected"] = index
            errors.append(
                {
                    "symbol": "REMAINING",
                    "reason": "Scan time budget reached; remaining matches were not inspected.",
                }
            )
            break
        ticker = candidate["symbol"]
        try:
            if mode == "demo":
                clock, quote, daily, bars = demo_observations(*demo_specs[ticker])
            else:
                quote, daily, bars = fetch_live_data(
                    ticker, provider.feed, now=now, provider=labeled, sessions=sessions
                )
                clock = datetime.now(UTC)
            warning = None
            try:
                report = build_report(
                    ticker, as_of=clock, quote=quote, daily_bars=daily, session_bars=bars
                )
            except ValueError:
                report = build_report(ticker, as_of=clock, quote=quote, daily_bars=daily)
                warning = "Incomplete intraday observations; no setup-derived plan."
            if bars and warning is None:
                report["intraday"]["last_close"] = str(bars[-1].close)
            report["premarket_research"] = premarket_research(bars, quote, clock)
            plan = derive_plan(
                report,
                account=account,
                holding=positions.get(ticker),
                context=context,
                demo=mode == "demo",
                now=now,
            )
            if broker and (not account or not context.get("losses_confirmed", False)):
                plan["risk"] = None
                plan["guardrails"] = None
                plan["state"] = "RISK BLOCKED"
                plan["sizing_reason"] = (
                    "Review broker account issues and confirm today’s realized losses before sizing. "
                    "Day P/L does not establish realized losses."
                )
            rows.append(
                candidate
                | {"quote": report["quote"], "plan": plan, "report": report, "warning": warning,
                   "chart": {"source": quote.source, "mode": mode,
                             "session": [chart_bar(b) for b in bars],
                             "daily": [chart_bar(b) for b in daily]}}
            )
        except MarketDataError as exc:
            errors.append({"symbol": ticker, "reason": str(exc)})
        except (ValueError, TypeError, KeyError, ArithmeticError):
            errors.append(
                {
                    "symbol": ticker,
                    "reason": "Data or plan unavailable; no candidate prices fabricated.",
                }
            )
    if mode == "live":
        completed = datetime.now(UTC)
        for row in rows:
            quote_time = datetime.fromisoformat(row["quote"]["timestamp"])
            if completed - quote_time > timedelta(seconds=60):
                row["report"]["quote"]["fresh"] = False
                row["plan"] = derive_plan(
                    row["report"],
                    account=account,
                    holding=positions.get(row["symbol"]),
                    context=context,
                    now=completed,
                )
    order = {
        "SETUP CONFIRMED": 0,
        "WATCH": 1,
        "RISK BLOCKED": 2,
        "SPREAD TOO WIDE": 3,
        "NO VALID SETUP": 4,
        "DATA UNAVAILABLE": 5,
    }
    rows.sort(
        key=lambda row: (
            order[row["plan"]["state"]],
            -Decimal(row["change_percent"]),
            row["symbol"],
        )
    )
    return {
        "mode": mode,
        "as_of": now.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "coverage": coverage,
        "candidates": rows,
        "errors": errors,
        "account_configured": bool(account),
        "broker_account": broker,
        "ready_to_trade": False,
        "ranking": "Eligible setup state, then snapshot percent change; no probability or profitability score.",
        "notice": "DEMO: fabricated stocks and observations."
        if mode == "demo"
        else (
            "Read-only Webull scan with broker-reported holdings. Stops and pending orders unverified."
            if broker
            else "Read-only market scan. Prices require revalidation before use. No broker positions or stops verified."
        ),
    }


def premarket_research(bars, quote, now):
    """Observed premarket slice only, independent of regular-session sizing."""
    from datetime import timedelta
    from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

    observed = [b for b in bars if b.session == "premarket"
                and b.timestamp + timedelta(minutes=1) <= now]
    if not observed:
        return None
    high, low = max(b.high for b in observed), min(b.low for b in observed)
    last = observed[-1].close
    tick = Decimal(".0001") if last < 1 else Decimal(".01")
    fresh = quote.session == "premarket" and timedelta(0) <= now - quote.timestamp <= timedelta(
        seconds=60)
    two_sided = quote.bid > 0 and quote.ask >= quote.bid
    spread = (quote.ask - quote.bid) / quote.ask * 100 if two_sided else None
    eligible = len(observed) >= 3 and fresh and spread is not None and spread <= 2 and high > low
    entry = (high / tick).to_integral_value(rounding=ROUND_CEILING) * tick + tick
    stop = (low / tick).to_integral_value(rounding=ROUND_FLOOR) * tick - tick
    eligible = eligible and stop > 0 and entry < 5
    return {"session": "premarket", "observed_bars": len(observed),
            "first_bar_at": observed[0].timestamp.isoformat(),
            "last_bar_at": observed[-1].timestamp.isoformat(), "last": str(last),
            "observed_volume": sum(int(b.volume) for b in observed),
            "observed_high": str(high), "observed_low": str(low),
            "spread_percent": str(spread) if spread is not None else None,
            "conditional_entry": str(entry) if eligible else None,
            "invalidation": str(stop) if eligible else None,
            "risk_per_share": str(entry - stop) if eligible else None,
            "quote_at": quote.timestamp.isoformat(),
            "note": "Observed premarket bars only; gaps and missing intervals may exist. "
                    "Levels require three bars and a fresh two-sided premarket quote with spread "
                    "at most 2%. Invalidation is not a verified broker stop. No position sizing."}


def chart_bar(bar):
    """JSON-safe actual OHLCV observations; never fill missing intervals."""
    return {"time": bar.timestamp.isoformat(), "open": str(bar.open),
            "high": str(bar.high), "low": str(bar.low), "close": str(bar.close),
            "volume": str(bar.volume), "session": bar.session, "interval": bar.interval}
