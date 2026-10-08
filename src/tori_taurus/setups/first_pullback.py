"""Proposed first-pullback rule with frozen impulse and retracement limits."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import pairwise

from tori_taurus.indicators.intraday import INTERVALS, _session
from tori_taurus.market_data import Bar
from tori_taurus.market_data.models import price, utc


@dataclass(frozen=True)
class PullbackConfig:
    impulse_bars: int = 3
    min_impulse_percent: Decimal = Decimal(5)
    max_retracement_percent: Decimal = Decimal(50)
    max_extension_percent: Decimal = Decimal(3)
    max_pullback_bars: int = 5
    max_observation_age: timedelta = timedelta(minutes=2)

    def __post_init__(self):
        for key in ("impulse_bars", "max_pullback_bars"):
            value = getattr(self, key)
            if type(value) is not int or value < (2 if key == "impulse_bars" else 1):
                raise ValueError("Invalid bar count")
        for key in ("min_impulse_percent", "max_retracement_percent", "max_extension_percent"):
            object.__setattr__(self, key, price(getattr(self, key)))
        if not 0 < self.max_retracement_percent < 100:
            raise ValueError("Retracement must be strictly between 0 and 100 percent")
        if self.max_observation_age < timedelta(0):
            raise ValueError("Observation age must be nonnegative")


def evaluate_first_pullback(
    bars: list[Bar], *, as_of: datetime, config: PullbackConfig | None = None
) -> dict:
    """First lower-close pullback after a qualifying initial rising-close impulse."""
    _session(bars)
    config, as_of = config or PullbackConfig(), utc(as_of)
    step = timedelta(minutes=INTERVALS[bars[0].interval])
    if any(b.timestamp + step > as_of for b in bars):
        raise ValueError("Only completed bars at or before as_of are allowed")
    end = bars[-1].timestamp + step
    if as_of - end > config.max_observation_age:
        raise ValueError("Setup observations are stale")
    state, reason = "UNAVAILABLE", "insufficient_impulse_history"
    peak, base, anchor, confirmation = None, None, None, None
    pullback, confirmed, invalidated, expired = None, None, None, None
    pullback_index = None
    if len(bars) >= config.impulse_bars:
        seed = bars[: config.impulse_bars]
        qualifies = (
            seed[0].close > 0
            and all(b.volume > 0 for b in seed)
            and all(b.close > a.close for a, b in pairwise(seed))
            and (seed[-1].close / seed[0].close - 1) * 100 >= config.min_impulse_percent
        )
        state, reason = "NO_SETUP", "initial_impulse_not_qualified"
        if qualifies:
            base, peak = min(b.low for b in seed), max(b.high for b in seed)
            state, reason = "IMPULSE", "await_first_lower_close"
            for index in range(config.impulse_bars, len(bars)):
                bar = bars[index]
                if state in {"INVALIDATED", "EXPIRED"}:
                    continue
                if pullback is None:
                    if bar.volume > 0 and bar.close < bars[index - 1].close:
                        pullback, pullback_index, confirmation = bar.timestamp, index, bar.high
                        anchor = peak - (peak - base) * config.max_retracement_percent / 100
                        state, reason = "WATCH", "await_later_close_above_first_pullback_high"
                    else:
                        if bar.volume > 0:
                            peak = max(peak, bar.high)
                        continue
                if bar.low <= anchor:
                    state, reason, invalidated = (
                        "INVALIDATED",
                        "retracement_anchor_touched",
                        bar.timestamp,
                    )
                    continue
                if confirmed is None and index - pullback_index > config.max_pullback_bars:
                    state, reason, expired = "EXPIRED", "confirmation_window_expired", bar.timestamp
                    continue
                extension = (bar.close / peak - 1) * 100 if peak > 0 else Decimal(0)
                if extension > config.max_extension_percent:
                    state, reason = "EXTENDED", "extension_above_limit"
                elif index > pullback_index and bar.volume > 0 and bar.close > confirmation:
                    if confirmed is None:
                        confirmed = bar.timestamp
                    state, reason = "CONFIRMED", "later_close_above_first_pullback_high"
                elif confirmed is not None:
                    state, reason = "CONFIRMED", "confirmation_holds_until_anchor_invalidation"
                else:
                    state, reason = "WATCH", "await_later_close_above_first_pullback_high"
    return {
        "setup": "first_pullback",
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
        "impulse_base": str(base) if base is not None else None,
        "impulse_peak": str(peak) if peak is not None else None,
        "invalidation_level": str(anchor) if anchor is not None else None,
        "confirmation_level": str(confirmation) if confirmation is not None else None,
        "pullback_at": pullback.isoformat() if pullback else None,
        "confirmed_at": confirmed.isoformat() if confirmed else None,
        "invalidated_at": invalidated.isoformat() if invalidated else None,
        "expired_at": expired.isoformat() if expired else None,
        "parameters": {
            "impulse_bars": config.impulse_bars,
            "min_impulse_percent": str(config.min_impulse_percent),
            "max_retracement_percent": str(config.max_retracement_percent),
            "max_extension_percent": str(config.max_extension_percent),
            "max_pullback_bars": config.max_pullback_bars,
        },
        "confirmation": "Later nonzero-volume close strictly above first pullback high, within extension and time limits.",
        "invalidation": "Low at/below the frozen impulse retracement anchor, including on first pullback bar.",
        "note": "Proposed research rule; no broker stop, position sizing or execution.",
    }
