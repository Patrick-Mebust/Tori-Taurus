"""Bounded snapshot filters shared by the live discovery adapters."""

from dataclasses import dataclass
from decimal import Decimal

from tori_taurus.market_data.models import price


@dataclass(frozen=True)
class DiscoveryFilters:
    min_price: Decimal = Decimal(".01")
    max_price: Decimal = Decimal(5)  # Exclusive upper bound.
    min_change_percent: Decimal = Decimal(0)
    min_volume: int = 100000
    max_candidates: int = 20

    def __post_init__(self):
        for name in ("min_price", "max_price", "min_change_percent"):
            object.__setattr__(self, name, price(getattr(self, name)))
        if not Decimal(".01") <= self.min_price < self.max_price <= 5:
            raise ValueError("Scan prices must satisfy 0.01 <= minimum < maximum <= 5")
        if type(self.min_volume) is not int or not 0 <= self.min_volume <= 1000000000000:
            raise ValueError("Scan minimum volume must be a nonnegative whole number")
        if type(self.max_candidates) is not int or self.max_candidates not in {20, 40, 60}:
            raise ValueError("Scan depth must be 20, 40 or 60")

    @classmethod
    def from_payload(cls, values):
        if values is None:
            return cls()
        if not isinstance(values, dict) or set(values) - set(cls.__dataclass_fields__):
            raise ValueError("Invalid scanner filters")
        values = dict(values)
        for name in ("min_volume", "max_candidates"):
            if name in values:
                value = values[name]
                if isinstance(value, bool):
                    raise ValueError("Whole-number scanner filter required")
                numeric = price(value)
                maximum = 60 if name == "max_candidates" else 1000000000000
                if numeric > maximum or numeric != numeric.to_integral_value():
                    raise ValueError("Whole-number scanner filter required")
                values[name] = int(numeric)
        return cls(**values)

    def matches(self, last, change, volume):
        return (
            self.min_price <= last < self.max_price
            and change > 0
            and change >= self.min_change_percent
            and volume >= self.min_volume
        )

    def as_dict(self):
        return {
            "min_price": str(self.min_price),
            "max_price": str(self.max_price),
            "min_change_percent": str(self.min_change_percent),
            "min_volume": self.min_volume,
            "max_candidates": self.max_candidates,
        }
