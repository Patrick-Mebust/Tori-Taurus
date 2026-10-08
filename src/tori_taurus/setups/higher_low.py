"""Delayed pivot recognition for a proposed higher-low continuation rule."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from tori_taurus.indicators.intraday import INTERVALS, _session
from tori_taurus.market_data import Bar
from tori_taurus.market_data.models import price, utc


@dataclass(frozen=True)
class HigherLowConfig:
    pivot_width: int = 1
    min_low_improvement_percent: Decimal = Decimal(0)
    max_extension_percent: Decimal = Decimal(3)
    max_observation_age: timedelta = timedelta(minutes=2)

    def __post_init__(self):
        if type(self.pivot_width) is not int or self.pivot_width < 1:
            raise ValueError("Pivot width must be a positive integer")
        for key in ("min_low_improvement_percent", "max_extension_percent"):
            object.__setattr__(self, key, price(getattr(self, key)))
        if self.max_observation_age < timedelta(0):
            raise ValueError("Observation age must be nonnegative")


def evaluate_higher_low(
    bars: list[Bar], *, as_of: datetime, config: HigherLowConfig | None = None
) -> dict:
    """Recognize pivots only after right-side bars complete; later close confirms."""
    _session(bars)
    config, as_of = config or HigherLowConfig(), utc(as_of)
    step = timedelta(minutes=INTERVALS[bars[0].interval])
    if any(b.timestamp + step > as_of for b in bars):
        raise ValueError("Only completed bars at or before as_of are allowed")
    end = bars[-1].timestamp + step
    if as_of - end > config.max_observation_age:
        raise ValueError("Setup observations are stale")
    width = config.pivot_width
    state, reason = "NO_SETUP", "await_two_qualified_pivot_lows"
    if len(bars) < 2 * width + 1:
        state, reason = "UNAVAILABLE", "insufficient_pivot_history"
    previous_pivot, first_pivot, second_pivot = None, None, None
    anchor, level, identified_index = None, None, None
    identified, confirmed, invalidated = None, None, None
    for index, bar in enumerate(bars):
        if state == "INVALIDATED":
            continue
        if identified is not None:
            if bar.low <= anchor:
                state, reason, invalidated = (
                    "INVALIDATED",
                    "higher_low_anchor_touched",
                    bar.timestamp,
                )
                continue
            extension = (bar.close / level - 1) * 100
            if extension > config.max_extension_percent:
                state, reason = "EXTENDED", "extension_above_limit"
            elif index > identified_index and bar.volume > 0 and bar.close > level:
                if confirmed is None:
                    confirmed = bar.timestamp
                state, reason = "CONFIRMED", "later_close_above_intervening_high"
            elif confirmed is not None:
                state, reason = "CONFIRMED", "confirmation_holds_until_anchor_invalidation"
            else:
                state, reason = "WATCH", "await_later_close_above_intervening_high"
            continue
        if index < 2 * width:
            continue
        center = index - width
        window = bars[center - width : center + width + 1]
        pivot = bars[center]
        is_low = all(b.volume > 0 for b in window) and all(
            pivot.low < b.low for i, b in enumerate(window) if i != width
        )
        if not is_low:
            continue
        if previous_pivot is not None:
            previous = bars[previous_pivot]
            qualifies = (
                previous.low > 0
                and pivot.low > previous.low
                and (pivot.low / previous.low - 1) * 100 >= config.min_low_improvement_percent
            )
            if qualifies:
                level = max(b.high for b in bars[previous_pivot + 1 : center])
                anchor = pivot.low
                first_pivot, second_pivot = previous_pivot, center
                identified, identified_index = bar.timestamp + step, index
                state, reason = "WATCH", "higher_low_known_await_later_confirmation"
        previous_pivot = center
    return {
        "setup": "higher_low_continuation",
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
        "first_pivot_at": bars[first_pivot].timestamp.isoformat()
        if first_pivot is not None
        else None,
        "higher_low_at": bars[second_pivot].timestamp.isoformat()
        if second_pivot is not None
        else None,
        "identified_at": identified.isoformat() if identified else None,
        "confirmed_at": confirmed.isoformat() if confirmed else None,
        "invalidated_at": invalidated.isoformat() if invalidated else None,
        "invalidation_level": str(anchor) if anchor is not None else None,
        "confirmation_level": str(level) if level is not None else None,
        "parameters": {
            "pivot_width": width,
            "min_low_improvement_percent": str(config.min_low_improvement_percent),
            "max_extension_percent": str(config.max_extension_percent),
        },
        "confirmation": "After higher low is known, a later nonzero-volume close above the frozen intervening high within extension limit.",
        "invalidation": "Any subsequent low at/below the frozen higher-low anchor.",
        "note": "Pivot timestamp differs from recognition time; research only, no broker stop or order.",
    }
