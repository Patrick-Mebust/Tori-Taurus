"""Decimal calculations with explicit warm-up and homogeneous bar input."""

import itertools
from decimal import Decimal
from zoneinfo import ZoneInfo

from tori_taurus.market_data import Bar


def validate_bars(bars: list[Bar]) -> None:
    if not bars:
        raise ValueError("Bars are required")
    identity = {(b.symbol, b.interval, b.source, b.mode) for b in bars}
    if len(identity) != 1:
        raise ValueError("Bars must share symbol, interval, source and mode")
    times = [b.timestamp for b in bars]
    if times != sorted(set(times)):
        raise ValueError("Bars must be strictly chronological and unique")


def _period(period: int) -> None:
    if type(period) is not int or period < 1:
        raise ValueError("Period must be a positive integer")


def ema(bars: list[Bar], period: int) -> Decimal | None:
    """Latest EMA, seeded by the first period's SMA; None before warm-up."""
    validate_bars(bars)
    _period(period)
    if len(bars) < period:
        return None
    value = sum((b.close for b in bars[:period]), Decimal(0)) / period
    alpha = Decimal(2) / (period + 1)
    for bar in bars[period:]:
        value += alpha * (bar.close - value)
    return value


def rsi(bars: list[Bar], period: int = 14) -> Decimal | None:
    """Wilder RSI from period price changes; flat gain/loss is defined as 50."""
    validate_bars(bars)
    _period(period)
    if len(bars) <= period:
        return None
    changes = [b.close - a.close for a, b in itertools.pairwise(bars)]
    gain = sum((max(c, Decimal(0)) for c in changes[:period]), Decimal(0)) / period
    loss = sum((max(-c, Decimal(0)) for c in changes[:period]), Decimal(0)) / period
    for change in changes[period:]:
        gain = (gain * (period - 1) + max(change, Decimal(0))) / period
        loss = (loss * (period - 1) + max(-change, Decimal(0))) / period
    if gain == loss == 0:
        return Decimal(50)
    if loss == 0:
        return Decimal(100)
    return Decimal(100) - Decimal(100) / (1 + gain / loss)


def atr(bars: list[Bar], period: int = 14) -> Decimal | None:
    """Wilder ATR; first true range uses high-low (no preceding close)."""
    validate_bars(bars)
    _period(period)
    if len(bars) < period:
        return None
    ranges = [bars[0].high - bars[0].low]
    for previous, current in itertools.pairwise(bars):
        ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    value = sum(ranges[:period], Decimal(0)) / period
    for true_range in ranges[period:]:
        value = (value * (period - 1) + true_range) / period
    return value


def vwap(bars: list[Bar]) -> Decimal | None:
    """Bar-based typical-price VWAP for one explicitly labeled intraday session."""
    validate_bars(bars)
    if bars[0].interval == "1d":
        raise ValueError("VWAP requires intraday bars")
    if len({b.session for b in bars}) != 1 or bars[0].session not in {
        "premarket",
        "regular",
        "postmarket",
    }:
        raise ValueError("VWAP requires one known session")
    zone = ZoneInfo("America/New_York")
    if len({b.timestamp.astimezone(zone).date() for b in bars}) != 1:
        raise ValueError("VWAP cannot span Eastern trading dates")
    volume = sum(b.volume for b in bars)
    if volume == 0:
        return None
    return sum(((b.high + b.low + b.close) / 3 * b.volume for b in bars), Decimal(0)) / volume
