"""Read-only Webull OpenAPI adapter. No order endpoints or private-data logging."""

import io
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from .alpaca import MarketDataError
from .models import Bar, Quote, price, symbol, utc


def credentials_available():
    return all(os.environ.get(k, "").strip() for k in ("WEBULL_APP_KEY", "WEBULL_APP_SECRET"))


def _number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Non-finite broker value")
    return result


class WebullProvider:
    feed = "webull"
    source = "webull:openapi"

    def __init__(self, *, data=None, account=None):
        if data is not None and account is not None:
            self.data, self.account = data, account
            return
        if not credentials_available():
            raise MarketDataError(
                "Webull API keys are not configured locally. Complete API activation first."
            )
        try:
            from webull.core.client import ApiClient
            from webull.data.data_client import DataClient
            from webull.trade.trade.v2.account_info_v2 import AccountV2

            client = ApiClient(
                os.environ["WEBULL_APP_KEY"],
                os.environ["WEBULL_APP_SECRET"],
                "us",
                connect_timeout=5,
                timeout=10,
                auto_retry=False,
                token_check_duration_seconds=30,
            )
            # Configure before SDK client initialization, which otherwise enables file logging.
            client.set_stream_logger(log_level=100, stream=io.StringIO())
            client.add_endpoint("us", "api.webull.com")
            token_root = (
                Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ToriTaurus" / "webull-auth"
            )
            client.set_token_dir(str(token_root))
            if os.environ.get("WEBULL_ACCESS_TOKEN"):
                client.set_token(os.environ["WEBULL_ACCESS_TOKEN"])
            self.data = DataClient(client)
            self.account = AccountV2(client)
        except ImportError:
            raise MarketDataError(
                "Install Tori with the webull extra to enable this connection."
            ) from None
        except Exception as exc:  # noqa: BLE001 - redact SDK messages at boundary
            code = getattr(exc, "error_code", None)
            if code in {"ERROR_INIT_TOKEN", "ERROR_CHECK_TOKEN"}:
                raise MarketDataError(
                    "Webull verification is pending or expired. Approve the request in your Webull app, "
                    "then click Refresh my account. Keep 2FA enabled."
                ) from None
            raise MarketDataError(
                "Webull authentication unavailable. Check API activation, keys and app verification."
            ) from None

    @staticmethod
    def call(method, *args, **kwargs):
        try:
            response = method(*args, **kwargs)
            if response.status_code == 403:
                raise MarketDataError(
                    "Webull access denied. Check OpenAPI permissions and market-data entitlement."
                )
            if response.status_code != 200:
                raise MarketDataError(
                    "Webull request unavailable. Check authentication or retry later."
                )
            return response.json()
        except MarketDataError:
            raise
        except Exception as exc:  # noqa: BLE001 - never expose SDK response messages
            stage = {
                "list_most_active": "most-active stock discovery",
                "list_gainers_losers": "gainers discovery",
                "get_snapshot": "stock snapshots",
                "get_batch_history_bar": "price history",
                "get_account_list": "account list",
                "get_account_balance": "account balance",
                "get_account_position": "holdings",
            }.get(getattr(method, "__name__", ""), "data request")
            status = getattr(exc, "http_status", None)
            if status == 403:
                reason = "Access denied. Check the Webull OpenAPI market-data subscription and API permissions."
            elif status == 401:
                reason = "Authentication expired or rejected. Refresh the connection and complete Webull verification."
            elif status == 429:
                reason = "Webull rate limit reached. Wait a minute before retrying."
            elif status in (400, 404, 405, 417, 422):
                reason = "Webull rejected this request (HTTP " + str(status) + ")."
            elif status in (500, 502, 503, 504):
                reason = "Webull service is temporarily unavailable."
            else:
                reason = "Connection or SDK request failed. Private response details are withheld."
            raise MarketDataError("Webull " + stage + ": " + reason) from None

    def list_accounts(self):
        accounts = self.call(self.account.get_account_list)
        if not isinstance(accounts, list):
            raise MarketDataError("Webull account-list format is unsupported; no account assumed.")
        return [
            {
                "id": row["account_id"],
                "label": str(row.get("account_type", "Account"))
                + " • ending "
                + str(row.get("account_number", ""))[-4:],
            }
            for row in accounts
        ]

    def account_snapshot(self):
        accounts = self.call(self.account.get_account_list)
        selected = os.environ.get("WEBULL_ACCOUNT_ID")
        matches = [a for a in accounts if not selected or a["account_id"] == selected]
        if len(matches) != 1:
            raise MarketDataError("Select one Webull account using WEBULL_ACCOUNT_ID locally.")
        account_id = matches[0]["account_id"]
        balance = self.call(self.account.get_account_balance, account_id)
        holdings = self.call(self.account.get_account_position, account_id)
        try:
            if balance["total_asset_currency"] != "USD":
                raise ValueError("USD required")
            usd = [a for a in balance["account_currency_assets"] if a["currency"] == "USD"]
            if len(usd) != 1:
                raise ValueError("USD balance unavailable")
            # Overnight buying power is the conservative cap for conditional stock plans.
            buying_power = min(
                price(usd[0]["day_buying_power"]), price(usd[0]["overnight_buying_power"])
            )
            positions, sizing_issues = [], []
            for row in holdings:
                qty = _number(row["quantity"])
                average = price(row["cost_price"])
                ticker = symbol(row["symbol"])
                if (
                    qty < 0
                    or qty != qty.to_integral_value()
                    or row["currency"] != "USD"
                    or row["instrument_type"] != "EQUITY"
                ):
                    sizing_issues.append(
                        "Unsupported holding type or fractional/short position; sizing disabled."
                    )
                positions.append(
                    {
                        "symbol": ticker,
                        "shares": str(qty),
                        "average": str(average),
                        "market_value": str(_number(row["market_value"])),
                        "unrealized_pnl": str(_number(row["unrealized_profit_loss"])),
                    }
                )
            if balance.get("open_margin_calls"):
                sizing_issues.append("Webull reports an open margin call; sizing disabled.")
            return {
                "source": self.source,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "equity": str(price(balance["total_net_liquidation_value"])),
                "buying_power": str(buying_power),
                "cash": str(_number(balance["total_cash_balance"])),
                "day_pnl": str(_number(balance["total_day_profit_loss"])),
                "holdings": positions,
                "sizing_issues": sorted(set(sizing_issues)),
                "notice": "Broker-reported values at retrieval. Day P/L is not realized losses. Stops and pending orders are unverified.",
            }
        except (KeyError, ValueError, TypeError, ArithmeticError):
            raise MarketDataError(
                "Webull account fields are incomplete or unsupported; no account values assumed."
            ) from None

    def snapshots(self, tickers):
        return self.call(
            self.data.market_data.get_snapshot,
            tickers,
            "US_STOCK",
            extend_hour_required=True,
            overnight_required=False,
        )

    def get_quote(self, ticker):
        ticker = symbol(ticker)
        rows = self.snapshots([ticker])
        try:
            (row,) = [r for r in rows if r["symbol"] == ticker]
            return Quote(
                ticker,
                datetime.fromtimestamp(int(row["quote_time"]) / 1000, UTC),
                row["bid"],
                row["ask"],
                self.source,
                mode="live",
            )
        except (ValueError, KeyError, TypeError, ArithmeticError):
            raise MarketDataError("Webull quote missing or invalid.") from None

    def get_bars(self, ticker, start, end, interval="1d"):
        ticker = symbol(ticker)
        if interval not in {"1d", "1m"}:
            raise ValueError("Unsupported Webull interval")
        local_start = start.astimezone(ZoneInfo("America/New_York"))
        session_code = "PRE" if interval == "1m" and (local_start.hour, local_start.minute) < (9, 30) else "RTH"
        payload = self.call(
            self.data.market_data.get_batch_history_bar,
            [ticker],
            "US_STOCK",
            "D" if interval == "1d" else "M1",
            count="1200" if interval == "1d" else "1650",
            real_time_required=False,
            trading_sessions=session_code,
            start_time=int(utc(start).timestamp() * 1000),
            end_time=int(utc(end).timestamp() * 1000),
        )
        try:
            (group,) = [g for g in payload["result"] if g["symbol"] == ticker]
            if group["delay_minutes"] != 0:
                raise ValueError("Delayed bars")
            bars = []
            for row in group["result"]:
                timestamp = utc(datetime.fromisoformat(row["time"]))
                if not start <= timestamp < end:
                    continue
                volume = price(row["volume"])
                if interval != "1d" and volume != volume.to_integral_value():
                    raise ValueError("Invalid volume")
                if interval == "1m" and row["trading_session"] != session_code:
                    raise ValueError("Unexpected session")
                bars.append(
                    Bar(
                        ticker,
                        timestamp,
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        volume if interval == "1d" else int(volume),
                        interval,
                        self.source,
                        mode="live",
                        volume_adjusted=interval == "1d",
                    )
                )
            bars.sort(key=lambda b: b.timestamp)
            if len({b.timestamp for b in bars}) != len(bars):
                raise ValueError("Duplicate bars")
            return bars
        except (KeyError, ValueError, TypeError, ArithmeticError):
            raise MarketDataError("Webull bars delayed, missing or invalid.") from None

    def discover(self, filters=None):
        from tori_taurus.scanner.filters import DiscoveryFilters

        filters = filters or DiscoveryFilters()
        active = self.call(
            self.data.screener.list_most_active,
            "US_STOCK",
            rank_type="VOLUME",
            sort_by="VOLUME",
            direction="DESC",
        )
        gainers = self.call(
            self.data.screener.list_gainers_losers,
            "DAY_1",
            "US_STOCK",
            "CHANGE_RATIO",
            direction="DESC",
        )
        try:
            if not isinstance(active, list) or not isinstance(gainers, list):
                raise MarketDataError("Webull discovery lists have an unsupported format. Retry later.")
            listing_rows_returned = len(active) + len(gainers)
            active, gainers = active[:200], gainers[:200]
            tickers_set, invalid_listing_rows = set(), 0
            for listing in active + gainers:
                try:
                    tickers_set.add(symbol(listing["symbol"]))
                except (KeyError, ValueError, TypeError, AttributeError):
                    invalid_listing_rows += 1
            if active + gainers and not tickers_set:
                raise MarketDataError("Webull discovery lists contain no usable stock symbols.")
            tickers = sorted(tickers_set)
            if len(tickers) > 400:
                raise ValueError("Unexpected discovery size")
            rows = []
            for offset in range(0, len(tickers), 100):
                batch = self.snapshots(tickers[offset : offset + 100])
                if not isinstance(batch, list):
                    raise MarketDataError("Webull stock snapshots have an unsupported format. Retry later.")
                rows.extend(batch)
            candidates, usable_symbols, invalid_snapshot_rows = [], set(), 0
            for row in rows:
                try:
                    ticker = symbol(row["symbol"])
                    if ticker not in tickers_set:
                        raise ValueError("Unrequested stock")
                    last, previous, volume = (
                        price(row["price"]), price(row["pre_close"]), price(row["volume"])
                    )
                    if last <= 0 or previous <= 0 or volume != volume.to_integral_value():
                        raise ValueError("Incomplete snapshot")
                    if ticker in usable_symbols:
                        continue
                    usable_symbols.add(ticker)
                    change = (last / previous - 1) * 100
                    if filters.matches(last, change, volume):
                        candidates.append({"symbol": ticker, "last": str(last),
                                           "change_percent": str(change), "volume": int(volume)})
                except (KeyError, ValueError, TypeError, ArithmeticError, AttributeError):
                    invalid_snapshot_rows += 1
            if tickers and not usable_symbols:
                raise MarketDataError(
                    "Webull returned no usable stock snapshots. Price, previous close or volume "
                    "was missing or invalid. Retry later; this is not a zero-match scan."
                )
            missing_snapshots = len(tickers_set - usable_symbols)
            candidates.sort(key=lambda r: (-Decimal(r["change_percent"]), r["symbol"]))
            depth = filters.max_candidates
            return candidates[:depth], {
                "universe": "Webull top 200 most active and top 200 gainers; not the full market",
                "discovered": len(tickers),
                "matched": len(candidates),
                "listing_rows_returned": listing_rows_returned,
                "listing_rows_considered": len(active) + len(gainers),
                "invalid_listing_rows": invalid_listing_rows,
                "invalid_snapshot_rows": invalid_snapshot_rows,
                "missing_snapshots": missing_snapshots,
                "inspected": min(depth, len(candidates)),
                "not_inspected": max(0, len(candidates) - depth),
                "filters": filters.as_dict(),
                "analysis_feed": self.source,
                "limits": f"Excluded {invalid_listing_rows} invalid discovery rows and {invalid_snapshot_rows} invalid snapshot rows; {missing_snapshots} discovered stocks lacked usable snapshots. Up to {depth} matches inspected within a 90-second detail budget. Partial-day volume; float, news and halts unverified. Daily bars and volume use Webull adjustment; minute bars are unadjusted.",
            }
        except (KeyError, ValueError, TypeError, ArithmeticError):
            raise MarketDataError("Webull discovery response unavailable or invalid.") from None
