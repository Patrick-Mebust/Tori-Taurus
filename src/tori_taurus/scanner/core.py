"""Historical daily candidate filter. Matches are research candidates only."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from tori_taurus.indicators.core import atr, ema, rsi, validate_bars
from tori_taurus.market_data import Bar
from tori_taurus.market_data.models import price, utc


def scan_daily(
    histories: dict[str, list[Bar]], *, as_of: datetime, config: "ScanConfig | None" = None
) -> list[dict]:
    """Evaluate a caller-supplied universe in ticker order; include rejected results."""
    results = []
    for ticker, bars in sorted(histories.items()):
        result = evaluate_daily(bars, as_of=as_of, config=config)
        if result["symbol"] != ticker:
            raise ValueError("Universe key must match normalized bar symbol")
        results.append(result)
    return results


@dataclass(frozen=True)
class ScanConfig:
    min_price: Decimal = Decimal("0.01")
    max_price: Decimal = Decimal(5)
    min_volume: int = 0
    min_change_percent: Decimal = Decimal(0)
    min_relative_volume: Decimal | None = None
    volume_lookback: int = 20

    def __post_init__(self):
        for name in ("min_price", "max_price"):
            object.__setattr__(self, name, price(getattr(self, name)))
        if not 0 < self.min_price < self.max_price:
            raise ValueError("Invalid price bounds")
        if type(self.min_volume) is not int or self.min_volume < 0:
            raise ValueError("Minimum volume must be a nonnegative integer")
        if type(self.volume_lookback) is not int or self.volume_lookback < 1:
            raise ValueError("Volume lookback must be a positive integer")
        change = Decimal(str(self.min_change_percent))
        if not change.is_finite():
            raise ValueError("Change threshold must be finite")
        object.__setattr__(self, "min_change_percent", change)
        if self.min_relative_volume is not None:
            object.__setattr__(self, "min_relative_volume", price(self.min_relative_volume))


def evaluate_daily(bars: list[Bar], *, as_of: datetime, config: ScanConfig | None = None) -> dict:
    """Latest supplied daily close; never implies a fresh quote or execution signal."""
    validate_bars(bars)
    as_of = utc(as_of)
    config = config or ScanConfig()
    if bars[0].interval != "1d" or any(b.timestamp > as_of for b in bars):
        raise ValueError("Daily bars at or before as_of are required")
    latest = bars[-1]
    previous = bars[-2] if len(bars) > 1 else None
    change = (
        (latest.close / previous.close - 1) * 100
        if previous is not None and previous.close > 0
        else None
    )
    gap = (
        (latest.open / previous.close - 1) * 100
        if previous is not None and previous.close > 0
        else None
    )
    baseline = bars[-config.volume_lookback - 1 : -1]
    relative = None
    if len(baseline) == config.volume_lookback:
        mean = Decimal(sum(b.volume for b in baseline)) / config.volume_lookback
        if mean > 0:
            relative = Decimal(latest.volume) / mean
    reasons = []
    if not config.min_price <= latest.close < config.max_price:
        reasons.append("price_outside_range")
    if latest.volume < config.min_volume:
        reasons.append("volume_below_minimum")
    if change is None:
        reasons.append("change_unavailable")
    elif change < config.min_change_percent:
        reasons.append("change_below_minimum")
    if config.min_relative_volume is not None:
        if relative is None:
            reasons.append("relative_volume_unavailable")
        elif relative < config.min_relative_volume:
            reasons.append("relative_volume_below_minimum")

    def number(value):
        return str(value) if value is not None else None

    return {
        "symbol": latest.symbol,
        "candidate": not reasons,
        "reasons": reasons,
        "as_of": as_of.isoformat(),
        "bar_timestamp": latest.timestamp.isoformat(),
        "source": latest.source,
        "mode": latest.mode,
        "basis": "supplied_daily_bars",
        "features": {
            "close": str(latest.close),
            "volume": str(latest.volume) if latest.volume_adjusted else latest.volume,
            "volume_basis": "adjusted" if latest.volume_adjusted else "unadjusted",
            "change_percent": number(change),
            "gap_percent": number(gap),
            "daily_relative_volume": number(relative),
            "ema5": number(ema(bars, 5)),
            "ema9": number(ema(bars, 9)),
            "ema20": number(ema(bars, 20)),
            "rsi14": number(rsi(bars)),
            "atr14": number(atr(bars)),
        },
        "note": "Research candidate only; daily bars may be partial or stale.",
    }
