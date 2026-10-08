"""Bounded Alpaca screener discovery; never a claim of full-market coverage."""

from datetime import datetime
from decimal import Decimal

from tori_taurus.market_data import MarketDataError
from tori_taurus.market_data.models import price, symbol, utc


def discover(provider):
    root = "https://data.alpaca.markets/v1beta1/screener/stocks/"
    active = provider._get_json(root + "most-actives?by=volume&top=100")
    movers = provider._get_json(root + "movers?top=50")
    try:
        active_at = utc(datetime.fromisoformat(active["last_updated"]))
        movers_at = utc(datetime.fromisoformat(movers["last_updated"]))
        if not isinstance(active["most_actives"], list) or not isinstance(movers["gainers"], list):
            raise TypeError("Invalid discovery lists")
        tickers = sorted(
            {symbol(row["symbol"]) for row in active["most_actives"] + movers["gainers"]}
        )
        if len(tickers) > 150:
            raise ValueError("Discovery exceeds advertised bounds")
    except (KeyError, TypeError, ValueError, AttributeError):
        raise MarketDataError("Invalid Alpaca discovery response") from None
    snapshots = (
        provider._request("snapshots", {"symbols": ",".join(tickers), "feed": provider.feed})
        if tickers
        else {}
    )
    candidates, rejected = [], []
    for ticker in tickers:
        try:
            snapshot = snapshots[ticker]
            trade, previous, day = (
                snapshot["latestTrade"],
                snapshot["prevDailyBar"],
                snapshot["dailyBar"],
            )
            last, previous_close = price(trade["p"]), price(previous["c"])
            observed = utc(datetime.fromisoformat(trade["t"]))
            volume = price(day["v"])
            if volume != volume.to_integral_value() or previous_close <= 0:
                raise ValueError("Invalid snapshot")
            change = (last / previous_close - 1) * 100
            if not Decimal(".01") <= last < 5 or change <= 0 or volume < 100000:
                rejected.append(
                    {
                        "symbol": ticker,
                        "reason": "Outside price, positive-change or 100,000-share volume filters",
                    }
                )
                continue
            candidates.append(
                {
                    "symbol": ticker,
                    "last": str(last),
                    "change_percent": str(change),
                    "volume": int(volume),
                    "observed_at": observed.isoformat(),
                }
            )
        except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
            rejected.append({"symbol": ticker, "reason": "Snapshot missing or invalid"})
    candidates.sort(
        key=lambda row: (-Decimal(row["change_percent"]), -row["volume"], row["symbol"])
    )
    return candidates[:20], {
        "universe": "Alpaca top 100 most-active stocks and top 50 gainers; not all listed stocks",
        "discovered": len(tickers),
        "matched": len(candidates),
        "inspected": min(20, len(candidates)),
        "not_inspected": max(0, len(candidates) - 20),
        "filtered": rejected,
        "most_active_updated_at": active_at.isoformat(),
        "movers_updated_at": movers_at.isoformat(),
        "discovery_source": "Alpaca SIP screeners",
        "analysis_feed": provider.feed,
        "limits": "Top 20 matches by snapshot change are inspected. Movers show the previous session until market open. Volume is a partial-day total, not relative volume. Equities can include ETFs; common-stock classification is not verified.",
    }
