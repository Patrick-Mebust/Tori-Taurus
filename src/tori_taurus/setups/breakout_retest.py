"""Proposed first-breakout rule with a frozen historical resistance level."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from tori_taurus.indicators.intraday import INTERVALS, _session
from tori_taurus.market_data import Bar
from tori_taurus.market_data.models import price, utc


@dataclass(frozen=True)
class BreakoutConfig:
    lookback_bars: int = 5
    retest_tolerance_percent: Decimal = Decimal("0.5")
    max_extension_percent: Decimal = Decimal(3)
    max_observation_age: timedelta = timedelta(minutes=2)

    def __post_init__(self):
        if type(self.lookback_bars) is not int or self.lookback_bars < 1:
            raise ValueError("Lookback must be a positive integer")
        for key in ("retest_tolerance_percent", "max_extension_percent"):
            object.__setattr__(self, key, price(getattr(self, key)))
        if self.retest_tolerance_percent >= 100:
            raise ValueError("Retest tolerance must be below 100 percent")
        if self.max_observation_age < timedelta(0):
            raise ValueError("Observation age must be nonnegative")


def evaluate_breakout_retest(
    bars: list[Bar], *, as_of: datetime, config: BreakoutConfig | None = None
) -> dict:
    """Seed resistance from initial lookback, then require distinct later bars."""
    _session(bars)
    config, as_of = config or BreakoutConfig(), utc(as_of)
    step = timedelta(minutes=INTERVALS[bars[0].interval])
    if any(b.timestamp + step > as_of for b in bars):
        raise ValueError("Only completed bars at or before as_of are allowed")
    end = bars[-1].timestamp + step
    if as_of - end > config.max_observation_age:
        raise ValueError("Setup observations are stale")
    enough = len(bars) > config.lookback_bars
    level = max(b.high for b in bars[: config.lookback_bars]) if enough else None
    anchor = level * (1 - config.retest_tolerance_percent / 100) if level is not None else None
    upper = level * (1 + config.retest_tolerance_percent / 100) if level is not None else None
    state, reason = "NO_SETUP", "no_close_above_frozen_resistance"
    breakout, retest, confirmed, invalidated = None, None, None, None
    confirmation_high = None
    if not enough:
        state, reason = "UNAVAILABLE", "insufficient_seed_and_observation_bars"
    elif level <= 0:
        state, reason = "UNAVAILABLE", "zero_resistance_level"
    else:
        for bar in bars[config.lookback_bars :]:
            if state == "INVALIDATED":
                continue
            if breakout is None:
                if bar.volume > 0 and bar.close > level:
                    breakout = bar.timestamp
                    state, reason = "WATCH", "await_later_retest"
            else:
                if bar.low <= anchor or bar.close < level:
                    state = "INVALIDATED"
                    reason = "anchor_touched" if bar.low <= anchor else "close_below_resistance"
                    invalidated = bar.timestamp
                    continue
                if retest is None:
                    if bar.volume > 0 and bar.low <= upper and bar.high >= level:
                        retest, confirmation_high = bar.timestamp, bar.high
                        state, reason = "RETEST", "await_later_close_above_retest_high"
                elif confirmed is None and bar.volume > 0 and bar.close > confirmation_high:
                    confirmed = bar.timestamp
                    state, reason = "CONFIRMED", "later_close_above_retest_high"
            if breakout is not None:
                extension = (bar.close / level - 1) * 100
                if extension > config.max_extension_percent:
                    # Excessive extension does not establish a new confirmation.
                    if confirmed == bar.timestamp:
                        confirmed = None
                    state, reason = "EXTENDED", "extension_above_limit"
                elif confirmed is not None:
                    state, reason = "CONFIRMED", "confirmation_holds_until_invalidation"
                elif retest is not None:
                    state, reason = "RETEST", "await_later_close_above_retest_high"
                else:
                    state, reason = "WATCH", "await_later_retest"
    if sum(b.volume for b in bars) == 0:
        state, reason = "UNAVAILABLE", "zero_observed_volume"
    return {
        "setup": "breakout_retest",
        "rule_version": "1.0",
        "state": state,
        "reason": reason,
        "symbol": bars[0].symbol,
        "source": bars[0].source,
        "mode": bars[0].mode,
        "session": bars[0].session,
        "as_of": as_of.isoformat(),
        "coverage_start": bars[0].timestamp.isoformat(),
        "coverage_end_exclusive": end.isoformat(),
        "resistance_level": str(level) if level is not None else None,
        "invalidation_level": str(anchor) if anchor is not None else None,
        "confirmation_level": str(confirmation_high) if confirmation_high is not None else None,
        "breakout_at": breakout.isoformat() if breakout else None,
        "retest_at": retest.isoformat() if retest else None,
        "confirmed_at": confirmed.isoformat() if confirmed else None,
        "invalidated_at": invalidated.isoformat() if invalidated else None,
        "lookback_bars": config.lookback_bars,
        "retest_tolerance_percent": str(config.retest_tolerance_percent),
        "max_extension_percent": str(config.max_extension_percent),
        "confirmation": "Breakout close above frozen resistance; later held retest; still later close above retest high within extension limit.",
        "invalidation": "After breakout, low at/below tolerance anchor or close below frozen resistance.",
        "note": "Research rule over supplied slice; no order, active stop, or profitability claim.",
    }
