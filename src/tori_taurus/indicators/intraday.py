"""Intraday observed-window features with matched Eastern wall-clock baselines."""

import itertools
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from tori_taurus.market_data import Bar
from tori_taurus.market_data.models import utc

from .core import validate_bars, vwap

INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
EASTERN = ZoneInfo("America/New_York")


def _session(bars: list[Bar]) -> None:
    validate_bars(bars)
    if bars[0].interval not in INTERVALS:
        raise ValueError("Intraday bars required")
    if len({b.session for b in bars}) != 1 or bars[0].session not in {
        "premarket",
        "regular",
        "postmarket",
    }:
        raise ValueError("One known session required")
    if len({b.timestamp.astimezone(EASTERN).date() for b in bars}) != 1:
        raise ValueError("One Eastern session date required")
    step = timedelta(minutes=INTERVALS[bars[0].interval])
    if any(b.timestamp - a.timestamp != step for a, b in itertools.pairwise(bars)):
        raise ValueError("Session slice must have contiguous interval starts")


def session_features(
    current: list[Bar],
    historical: list[list[Bar]],
    *,
    as_of: datetime,
    min_sessions: int = 5,
    acceleration_window: int = 3,
) -> dict:
    """Use completed bars only; never fill missing intervals with invented zeros."""
    _session(current)
    as_of = utc(as_of)
    if type(min_sessions) is not int or min_sessions < 1:
        raise ValueError("Minimum sessions must be a positive integer")
    if type(acceleration_window) is not int or acceleration_window < 1:
        raise ValueError("Acceleration window must be a positive integer")
    step = timedelta(minutes=INTERVALS[current[0].interval])
    if any(b.timestamp + step > as_of for b in current):
        raise ValueError("Current bars must be completed by as_of")
    current_date = current[0].timestamp.astimezone(EASTERN).date()
    slots = [b.timestamp.astimezone(EASTERN).time().replace(tzinfo=None) for b in current]
    identity = (
        current[0].symbol,
        current[0].interval,
        current[0].source,
        current[0].mode,
        current[0].session,
    )
    dates, volumes = set(), []
    for session in historical:
        _session(session)
        first = session[0]
        day = first.timestamp.astimezone(EASTERN).date()
        if day >= current_date or day in dates:
            raise ValueError("Baseline dates must be unique and earlier than current date")
        dates.add(day)
        if (first.symbol, first.interval, first.source, first.mode, first.session) != identity:
            raise ValueError("Baseline identity must match current session")
        lookup = {
            b.timestamp.astimezone(EASTERN).time().replace(tzinfo=None): b.volume for b in session
        }
        if all(slot in lookup for slot in slots):
            volumes.append(sum(lookup[slot] for slot in slots))
    observed_volume = sum(b.volume for b in current)
    relative, reason = None, None
    if len(volumes) < min_sessions:
        reason = "insufficient_matching_sessions"
    else:
        mean = Decimal(sum(volumes)) / len(volumes)
        if mean == 0:
            reason = "zero_baseline_volume"
        else:
            relative = Decimal(observed_volume) / mean
    acceleration, acceleration_reason = None, None
    if len(current) < 2 * acceleration_window:
        acceleration_reason = "insufficient_bars"
    else:
        prior = sum(b.volume for b in current[-2 * acceleration_window : -acceleration_window])
        if prior == 0:
            acceleration_reason = "zero_previous_window_volume"
        else:
            acceleration = Decimal(sum(b.volume for b in current[-acceleration_window:])) / prior
    return {
        "symbol": current[0].symbol,
        "source": current[0].source,
        "mode": current[0].mode,
        "session": current[0].session,
        "as_of": as_of.isoformat(),
        "coverage_start": current[0].timestamp.isoformat(),
        "coverage_end_exclusive": (current[-1].timestamp + step).isoformat(),
        "bar_count": len(current),
        "observed_volume": observed_volume,
        "observed_high": str(max(b.high for b in current)),
        "observed_low": str(min(b.low for b in current)),
        "vwap": str(vwap(current)) if observed_volume else None,
        "relative_volume": str(relative) if relative is not None else None,
        "relative_volume_reason": reason,
        "matching_baseline_sessions": len(volumes),
        "excluded_baseline_sessions": len(historical) - len(volumes),
        "volume_acceleration": str(acceleration) if acceleration is not None else None,
        "acceleration_window_bars": acceleration_window,
        "volume_acceleration_reason": acceleration_reason,
        "note": "Observed slice only; not proof of complete session coverage or a trade signal.",
    }
