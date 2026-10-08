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
            {"symbol": s, "change_percent": str(8 - i), "volume": 250000 - i * 20000}
            for i, (s, _, _) in enumerate(specs)
        ]
        coverage = {
            "universe": "Four fabricated scenarios, not real stocks",
            "discovered": 4,
            "matched": 4,
            "inspected": 4,
            "not_inspected": 0,
            "analysis_feed": "synthetic",
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
        candidates, coverage = discover(provider)
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
                clock, quote, daily, bars = demo_observations(*specs[index])
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
            plan = derive_plan(
                report,
                account=account,
                holding=positions.get(ticker),
                context=context,
                demo=mode == "demo",
                now=now,
            )
            rows.append(
                candidate
                | {"quote": report["quote"], "plan": plan, "report": report, "warning": warning}
            )
        except (MarketDataError, ValueError, TypeError, KeyError, ArithmeticError):
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
        "ready_to_trade": False,
        "ranking": "Eligible setup state, then snapshot percent change; no probability or profitability score.",
        "notice": "DEMO: fabricated stocks and observations."
        if mode == "demo"
        else "Read-only market scan. Prices require revalidation before use. No broker positions or stops verified.",
    }
