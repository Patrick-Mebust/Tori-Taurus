"""Versioned research rule, evaluated chronologically without future bars."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from tori_taurus.indicators.intraday import INTERVALS, _session
from tori_taurus.market_data import Bar
from tori_taurus.market_data.models import price, utc


@dataclass(frozen=True)
class ReclaimConfig:
    max_extension_percent: Decimal = Decimal(3)
    max_observation_age: timedelta = timedelta(minutes=2)

    def __post_init__(self):
        object.__setattr__(self, "max_extension_percent", price(self.max_extension_percent))
        if self.max_observation_age < timedelta(0):
            raise ValueError("Observation age must be nonnegative")


def evaluate_vwap_reclaim(
    bars: list[Bar], *, as_of: datetime, config: ReclaimConfig | None = None
) -> dict:
    """First reclaim in supplied session slice; no autonomous entry or stop order."""
    _session(bars)
    as_of, config = utc(as_of), config or ReclaimConfig()
    step = timedelta(minutes=INTERVALS[bars[0].interval])
    if any(b.timestamp + step > as_of for b in bars):
        raise ValueError("Only completed bars at or before as_of are allowed")
    end = bars[-1].timestamp + step
    if as_of - end > config.max_observation_age:
        raise ValueError("Setup observations are stale")
    state, reason = "NO_SETUP", "no_reclaim_cross"
    trigger, confirmed, invalidated = None, None, None
    anchor, trigger_high, previous_vwap, current_vwap = None, None, None, None
    cumulative_volume, cumulative_value = 0, Decimal(0)
    for index, bar in enumerate(bars):
        cumulative_volume += bar.volume
        cumulative_value += (bar.high + bar.low + bar.close) / 3 * bar.volume
        current_vwap = cumulative_value / cumulative_volume if cumulative_volume else None
        if state == "INVALIDATED":
            previous_vwap = current_vwap
            continue
        if trigger is not None:
            if bar.low <= anchor:
                state, reason, invalidated = "INVALIDATED", "anchor_low_touched", bar.timestamp
            elif current_vwap is not None and bar.close < current_vwap:
                state, reason, invalidated = "INVALIDATED", "close_below_vwap", bar.timestamp
            elif current_vwap is not None and current_vwap > 0:
                extension = (bar.close / current_vwap - 1) * 100
                if extension > config.max_extension_percent:
                    state, reason = "EXTENDED", "extension_above_limit"
                elif bar.volume > 0 and bar.close > trigger_high and bar.close > current_vwap:
                    state, reason = "CONFIRMED", "later_close_above_reclaim_high_and_vwap"
                    if confirmed is None:
                        confirmed = bar.timestamp
                elif confirmed is None:
                    state, reason = "WATCH", "await_later_close_above_reclaim_high_and_vwap"
                else:
                    state, reason = "CONFIRMED", "confirmation_holds_until_invalidation"
        elif (
            index > 0
            and bar.volume > 0
            and bars[index - 1].volume > 0
            and previous_vwap is not None
            and current_vwap is not None
            and bars[index - 1].close <= previous_vwap
            and bar.close > current_vwap
        ):
            trigger, anchor = bar.timestamp, min(bars[index - 1].low, bar.low)
            trigger_high = bar.high
            state, reason = "WATCH", "reclaim_cross_requires_later_confirmation"
            if (
                current_vwap > 0
                and (bar.close / current_vwap - 1) * 100 > config.max_extension_percent
            ):
                state, reason = "EXTENDED", "extension_above_limit"
        previous_vwap = current_vwap
    if cumulative_volume == 0:
        state, reason = "UNAVAILABLE", "zero_observed_volume"
    extension = (
        (bars[-1].close / current_vwap - 1) * 100
        if current_vwap is not None and current_vwap > 0
        else None
    )
    return {
        "setup": "vwap_reclaim",
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
        "trigger_at": trigger.isoformat() if trigger else None,
        "confirmed_at": confirmed.isoformat() if confirmed else None,
        "invalidated_at": invalidated.isoformat() if invalidated else None,
        "vwap": str(current_vwap) if current_vwap is not None else None,
        "extension_percent": str(extension) if extension is not None else None,
        "max_extension_percent": str(config.max_extension_percent),
        "confirmation_level": str(trigger_high) if trigger_high is not None else None,
        "invalidation_level": str(anchor) if anchor is not None else None,
        "confirmation": "A later completed close strictly above reclaim high and current VWAP, within extension limit.",
        "invalidation": "Any later low at/below anchor or close strictly below current VWAP.",
        "note": "Research state from supplied slice; anchor is not a broker stop or position sizing decision.",
    }
