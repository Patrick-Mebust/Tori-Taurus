"""Structured research report; no score, risk approval or order execution."""

import argparse
import json
from datetime import UTC, datetime, timedelta

from .behavior.guardrails import GuardrailInputs, evaluate_guardrails
from .indicators import session_features
from .market_data import Bar, MarketDataProvider, Quote, validate_freshness
from .market_data.models import symbol, utc
from .risk import RiskInputs, evaluate_risk
from .scanner import evaluate_daily
from .setups import (
    evaluate_breakout_retest,
    evaluate_first_pullback,
    evaluate_higher_low,
    evaluate_vwap_reclaim,
)


def build_report(
    ticker: str,
    *,
    as_of: datetime,
    quote: Quote | None = None,
    daily_bars: list[Bar] | None = None,
    session_bars: list[Bar] | None = None,
    baseline_sessions: list[list[Bar]] | None = None,
    max_quote_age: timedelta = timedelta(seconds=60),
    risk_inputs: RiskInputs | None = None,
    guardrail_inputs: GuardrailInputs | None = None,
) -> dict:
    """Join observations without promoting replay/stale data to a live decision."""
    ticker, as_of = symbol(ticker), utc(as_of)
    daily_bars, session_bars = daily_bars or [], session_bars or []
    baseline_sessions = baseline_sessions or []
    if max_quote_age < timedelta(0):
        raise ValueError("Maximum quote age must be nonnegative")
    all_bars = daily_bars + session_bars + [b for session in baseline_sessions for b in session]
    if any(b.symbol != ticker or b.timestamp > as_of for b in all_bars):
        raise ValueError("Mismatched ticker or future bar in report input")
    sources = {b.source for b in all_bars}
    if quote is not None:
        if quote.symbol != ticker:
            raise ValueError("Quote ticker mismatch")
        sources.add(quote.source)
    if len(sources) > 1:
        raise ValueError("Report observations must share one source/feed")
    quote_data = {"status": "unavailable", "reason": "quote_not_supplied", "fresh": False}
    if quote is not None:
        try:
            validate_freshness(quote, now=as_of, max_age=max_quote_age)
            fresh = True
        except ValueError:
            fresh = False
        quote_data = {
            "status": "available",
            "fresh": fresh,
            "source": quote.source,
            "mode": quote.mode,
            "timestamp": quote.timestamp.isoformat(),
            "bid": str(quote.bid),
            "ask": str(quote.ask),
            "session": quote.session,
            "reason": None if fresh else "quote_not_current_live_data",
        }
    daily = (
        evaluate_daily(daily_bars, as_of=as_of)
        if daily_bars
        else {"status": "unavailable", "reason": "daily_bars_not_supplied"}
    )
    intraday = {"status": "unavailable", "reason": "session_bars_not_supplied"}
    setups = {}
    evaluators = {
        "vwap_reclaim": evaluate_vwap_reclaim,
        "breakout_retest": evaluate_breakout_retest,
        "first_pullback": evaluate_first_pullback,
        "higher_low_continuation": evaluate_higher_low,
    }
    if session_bars:
        intraday = session_features(session_bars, baseline_sessions, as_of=as_of)
    for name, evaluate in evaluators.items():
        if not session_bars:
            setups[name] = {"state": "UNAVAILABLE", "reason": "session_bars_not_supplied"}
            continue
        try:
            setups[name] = evaluate(session_bars, as_of=as_of)
        except ValueError:
            # Intraday structural validation ran above; setup-specific age gates may fail.
            setups[name] = {"state": "UNAVAILABLE", "reason": "setup_observations_not_eligible"}
    risk = {"status": "unavailable", "reason": "account_and_trade_plan_not_supplied"}
    blockers = ["risk_not_evaluated"]
    if risk_inputs is not None:
        if risk_inputs.symbol != ticker:
            raise ValueError("Risk plan ticker mismatch")
        risk = evaluate_risk(risk_inputs)
        blockers = ["risk_inputs_unverified", "stop_not_broker_verified"] + risk["blockers"]
    guardrails = {"status": "unavailable", "reason": "guardrail_context_not_supplied"}
    if risk_inputs is not None and guardrail_inputs is not None:
        guardrails = evaluate_guardrails(risk_inputs, guardrail_inputs, as_of=as_of)
        blockers += guardrails["blockers"] + guardrails["unevaluated"]
    else:
        blockers.append("guardrails_not_evaluated")
    if not quote_data["fresh"]:
        blockers.append("no_fresh_live_quote")
    if not session_bars:
        blockers.append("no_session_observations")
    elif all(s["state"] == "UNAVAILABLE" for s in setups.values()):
        blockers.append("no_eligible_setup_observations")
    return {
        "schema_version": "1.0",
        "symbol": ticker,
        "as_of": as_of.isoformat(),
        "purpose": "research",
        "source": next(iter(sources)) if sources else None,
        "quote": quote_data,
        "daily_scan": daily,
        "intraday": intraday,
        "setups": setups,
        "risk": risk,
        "guardrails": guardrails,
        "decision": {"state": "RESEARCH_ONLY", "ready_to_trade": False, "blockers": blockers},
        "note": "No trade score, risk approval, broker stop or order is implied.",
    }


def report_from_provider(
    provider: MarketDataProvider,
    ticker: str,
    *,
    as_of: datetime,
    history_start: datetime,
    session_start: datetime,
    interval: str = "1m",
    session: str = "regular",
) -> dict:
    """Fetch read-only observations; use a calendar-labeled provider for intraday bars."""
    ticker, as_of = symbol(ticker), utc(as_of)
    history_start, session_start = utc(history_start), utc(session_start)
    if history_start >= as_of or session_start >= as_of:
        raise ValueError("Request starts must precede as_of")
    if session not in {"premarket", "regular", "postmarket"} or interval == "1d":
        raise ValueError("Known intraday session required")
    quote = provider.get_quote(ticker)
    daily = provider.get_bars(ticker, history_start, as_of, "1d")
    intraday = provider.get_bars(ticker, session_start, as_of, interval)
    if any(b.session == "unknown" for b in intraday):
        raise ValueError("Provider must label intraday sessions explicitly")
    selected = [b for b in intraday if b.session == session]
    return build_report(ticker, as_of=as_of, quote=quote, daily_bars=daily, session_bars=selected)


def demo_report(*, with_risk: bool = False) -> dict:
    """Fixed synthetic data makes the demonstration reproducible and visibly replay."""
    now = datetime(2026, 10, 7, 14, tzinfo=UTC)
    bars = [
        Bar(
            "DEMO",
            now - timedelta(minutes=6 - i),
            2,
            3,
            1,
            2,
            10,
            "1m",
            "synthetic:demo",
            session="regular",
        )
        for i in range(6)
    ]
    daily = [
        Bar(
            "DEMO",
            now - timedelta(days=2 - i),
            1 + i,
            2 + i,
            1 + i,
            2 + i,
            100,
            "1d",
            "synthetic:demo",
        )
        for i in range(2)
    ]
    quote = Quote("DEMO", now, 2, 3, "synthetic:demo", mode="replay")
    plan = (
        RiskInputs(
            "DEMO",
            equity=1000,
            buying_power=100,
            entry=3,
            requested_shares=5,
            stop=2,
            stop_reported_active=False,
        )
        if with_risk
        else None
    )
    return build_report(
        "DEMO", as_of=now, quote=quote, daily_bars=daily, session_bars=bars, risk_inputs=plan
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Print a reproducible synthetic Tori report")
    parser.add_argument(
        "--demo",
        action="store_true",
        required=True,
        help="Use fixed synthetic replay data; no network or credentials",
    )
    parser.add_argument("--with-risk", action="store_true", help="Include a synthetic account/plan")
    args = parser.parse_args(argv)
    print(json.dumps(demo_report(with_risk=args.with_risk), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
