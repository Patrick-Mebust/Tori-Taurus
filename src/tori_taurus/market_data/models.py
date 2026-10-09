"""Provider-neutral validated market records. Timestamps are always UTC."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


def symbol(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", value):
        raise ValueError("Invalid ticker")
    return value


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return value.astimezone(UTC)


def price(value: Decimal) -> Decimal:
    value = Decimal(str(value))
    if not value.is_finite() or value < 0:
        raise ValueError("Price must be finite and nonnegative")
    return value


@dataclass(frozen=True)
class Quote:
    symbol: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    source: str
    mode: str = "replay"
    session: str = "unknown"

    def __post_init__(self):
        object.__setattr__(self, "symbol", symbol(self.symbol))
        object.__setattr__(self, "timestamp", utc(self.timestamp))
        for key in ("bid", "ask"):
            object.__setattr__(self, key, price(getattr(self, key)))
        if self.bid > self.ask:
            raise ValueError("Bid exceeds ask")
        metadata(self.source, self.mode, self.session)


@dataclass(frozen=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | Decimal
    interval: str
    source: str
    mode: str = "replay"
    session: str = "unknown"
    volume_adjusted: bool = False

    def __post_init__(self):
        object.__setattr__(self, "symbol", symbol(self.symbol))
        object.__setattr__(self, "timestamp", utc(self.timestamp))
        for key in ("open", "high", "low", "close"):
            object.__setattr__(self, key, price(getattr(self, key)))
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Invalid OHLC range")
        if type(self.volume_adjusted) is not bool:
            raise ValueError("Invalid volume adjustment metadata")
        if self.volume_adjusted:
            if self.interval != "1d" or type(self.volume) not in {int, Decimal}:
                raise ValueError("Adjusted volume requires a daily numeric observation")
            object.__setattr__(self, "volume", price(self.volume))
        elif type(self.volume) is not int or self.volume < 0:
            raise ValueError("Unadjusted volume must be a nonnegative integer")
        if self.interval not in {"1m", "5m", "15m", "1h", "1d"}:
            raise ValueError("Unsupported interval")
        metadata(self.source, self.mode, self.session)


def metadata(source: str, mode: str, session: str) -> None:
    if not source.strip() or mode not in {"live", "delayed", "replay"}:
        raise ValueError("Invalid source or data mode")
    if session not in {"premarket", "regular", "postmarket", "closed", "unknown"}:
        raise ValueError("Invalid session")
