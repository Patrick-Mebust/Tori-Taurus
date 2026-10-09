"""Loopback-only local research beta. Account form data is never persisted."""

import argparse
import json
import os
import threading
import webbrowser
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from zoneinfo import ZoneInfo

from .behavior.guardrails import GuardrailInputs, evaluate_guardrails
from .market_data import AlpacaProvider, Bar, MarketDataError, NyseSessions, Quote, SessionProvider
from .market_data.models import symbol
from .market_data.webull import credentials_available as webull_credentials_available
from .report import build_report
from .risk import RiskInputs

SOCIAL_SCAN_LOCK = threading.Lock()


def credentials_available() -> bool:
    return bool(
        os.environ.get("ALPACA_API_KEY", "").strip()
        and os.environ.get("ALPACA_API_SECRET", "").strip()
    )


def _decimal(value) -> Decimal:
    if not isinstance(value, (str, int)) or isinstance(value, bool) or len(str(value)) > 40:
        raise ValueError("Use a decimal number")
    result = Decimal(str(value))
    if not result.is_finite() or abs(result) > Decimal(1000000000000):
        raise ValueError("Number outside beta input limits")
    return result


def _integer(value) -> int:
    number = _decimal(value)
    if number != number.to_integral_value() or not 0 <= number <= 1000000000:
        raise ValueError("Use nonnegative whole shares or minutes")
    return int(number)


def parse_inputs(payload: dict, ticker: str, reference: Decimal | None):
    fields = payload.get("plan", {})
    if not isinstance(fields, dict):
        raise TypeError("Plan must contain fields")
    plan = RiskInputs(
        ticker,
        equity=_decimal(fields.get("equity", "1000")),
        buying_power=_decimal(fields.get("buying_power", "100")),
        entry=_decimal(fields.get("entry", "2.10")),
        requested_shares=_integer(fields.get("requested_shares", "10")),
        stop=_decimal(fields["stop"]) if fields.get("stop") not in (None, "") else None,
        existing_shares=_integer(fields.get("existing_shares", "0")),
        existing_average=_decimal(fields.get("existing_average", "0")),
        risk_budget_percent=_decimal(fields.get("risk_budget_percent", "1")),
        max_concentration_percent=_decimal(fields.get("max_concentration_percent", "20")),
        stop_reported_active=False,
    )
    context = payload.get("guardrails", {})
    if not isinstance(context, dict):
        raise TypeError("Guardrails must contain fields")
    exit_text = context.get("last_exit_at")
    if exit_text and (not isinstance(exit_text, str) or len(exit_text) > 50):
        raise ValueError("Invalid last-exit timestamp")
    rails = GuardrailInputs(
        losses_today=_decimal(context.get("losses_today", "0")),
        daily_loss_limit_percent=_decimal(context.get("daily_loss_limit_percent", "3")),
        last_exit_at=datetime.fromisoformat(exit_text) if exit_text else None,
        cooldown_minutes=_integer(context.get("cooldown_minutes", "15")),
        reference_price=reference,
        max_chase_percent=_decimal(context.get("max_chase_percent", "3")),
        thesis_reconfirmed=context.get("thesis_reconfirmed", False),
    )
    return plan, rails


def demo_data(ticker: str, now: datetime):
    """One visibly fabricated regular-session scenario for every demo ticker."""
    # Fixed artificial session time/date, separate from the real request clock.
    start = datetime(2026, 10, 7, 14, tzinfo=UTC)
    closes = [
        "2.00",
        "1.98",
        "1.96",
        "1.99",
        "2.01",
        "2.03",
        "2.02",
        "2.00",
        "2.04",
        "2.06",
        "2.08",
        "2.07",
        "2.05",
        "2.09",
        "2.11",
        "2.10",
        "2.12",
        "2.13",
        "2.11",
        "2.14",
    ]
    current = [
        Bar(
            ticker,
            start + timedelta(minutes=i),
            c,
            Decimal(c) + Decimal(".02"),
            Decimal(c) - Decimal(".02"),
            c,
            1000 + i * 150,
            "1m",
            "synthetic:beta",
            session="regular",
        )
        for i, c in enumerate(closes)
    ]
    historical = [
        [
            Bar(
                ticker,
                b.timestamp - timedelta(days=d),
                b.open,
                b.high,
                b.low,
                b.close,
                1000,
                "1m",
                "synthetic:beta",
                session="regular",
            )
            for b in current
        ]
        for d in range(1, 6)
    ]
    daily = [
        Bar(
            ticker,
            start - timedelta(days=25 - i),
            "1.8",
            "2.2",
            "1.7",
            "2.0",
            50000 + i * 1000,
            "1d",
            "synthetic:beta",
        )
        for i in range(25)
    ]
    evaluated_at = current[-1].timestamp + timedelta(minutes=1)
    quote = Quote(
        ticker, evaluated_at, "2.13", "2.15", "synthetic:beta", mode="replay", session="regular"
    )
    return evaluated_at, quote, daily, current, historical


def fetch_live_data(ticker: str, feed: str, *, now: datetime, provider=None, sessions=None):
    """Completed regular-session snapshot with daily bars from previous dates only."""
    if provider is None and feed not in {"iex", "sip"}:
        raise ValueError("Unsupported feed")
    if provider is None:
        if not credentials_available():
            raise MarketDataError(
                "Live credentials are not configured. Use demo mode or configure them locally."
            )
        sessions = NyseSessions()
        provider = SessionProvider(
            AlpacaProvider(
                os.environ["ALPACA_API_KEY"],
                os.environ["ALPACA_API_SECRET"],
                feed=feed,
                max_pages=10,
            ),
            sessions,
        )
    zone = ZoneInfo("America/New_York")
    day = now.astimezone(zone).date()
    quote = provider.get_quote(ticker)
    daily = provider.get_bars(ticker, now - timedelta(days=60), now, "1d")
    daily = [b for b in daily if b.timestamp.astimezone(zone).date() < day]
    current = []
    bounds = sessions._bounds(day)
    if bounds is not None:
        _, opening, closing, _ = bounds
        end = min(now.replace(second=0, microsecond=0), closing)
        if end > opening:
            current = provider.get_bars(ticker, opening, end, "1m")
            current = [
                b
                for b in current
                if b.session == "regular"
                and b.timestamp >= opening
                and b.timestamp + timedelta(minutes=1) <= end
            ]
    return quote, daily, current


def evaluate_payload(payload: dict, *, now: datetime | None = None) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("Request must be an object")
    now = now or datetime.now(UTC)
    mode = payload.get("mode", "demo")
    ticker = symbol(payload.get("ticker", "DEMO"))
    if mode not in {"demo", "live"}:
        raise ValueError("Choose demo or live")
    if mode == "demo":
        clock, quote, daily, current, baselines = demo_data(ticker, now)
    else:
        quote, daily, current = fetch_live_data(ticker, payload.get("feed", "iex"), now=now)
        # Evaluate the actual quote after requests finish rather than before retrieval.
        clock, baselines = datetime.now(UTC), []
    plan, rails = parse_inputs(payload, ticker, current[-1].close if current else None)
    # Behavioral context uses the real request time; demo market rules use their fixed clock.
    quality = []
    try:
        report = build_report(
            ticker,
            as_of=clock,
            quote=quote,
            daily_bars=daily,
            session_bars=current,
            baseline_sessions=baselines,
            risk_inputs=plan,
        )
    except ValueError:
        if mode == "demo":
            raise
        # Sparse IEX/no-trade intervals cannot establish contiguous setup observations.
        report = build_report(ticker, as_of=clock, quote=quote, daily_bars=daily, risk_inputs=plan)
        quality.append(
            "Intraday observations were incomplete or ineligible; setup states are unavailable."
        )
    report["guardrails"] = evaluate_guardrails(plan, rails, as_of=now)
    report["decision"]["blockers"] = [
        b for b in report["decision"]["blockers"] if b != "guardrails_not_evaluated"
    ]
    report["decision"]["blockers"] += (
        report["guardrails"]["blockers"] + report["guardrails"]["unevaluated"]
    )
    confirmed = [name for name, state in report["setups"].items() if state["state"] == "CONFIRMED"]
    review = (
        "BLOCKED"
        if plan.stop is None or report["risk"]["blockers"] or report["guardrails"]["blockers"]
        else "RESEARCH ONLY"
    )
    report["beta"] = {
        "version": "0.3.0b1",
        "mode": mode,
        "requested_at": now.isoformat(),
        "review_status": review,
        "confirmed_setups": confirmed,
        "data_quality_warnings": quality,
        "live_connection_verified": mode == "live" and report["quote"]["fresh"],
        "chart_points": [
            {"timestamp": b.timestamp.isoformat(), "close": str(b.close)} for b in current
        ]
        if not quality
        else [],
        "notice": "Synthetic replay: no real ticker prices."
        if mode == "demo"
        else "Read-only Alpaca fetch. Account inputs and stops are not broker-verified.",
    }
    # User context never leaves this response and is never written to disk.
    return report


class BetaHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Never log submitted account inputs or provider messages.

    def _trusted(self) -> bool:
        expected = f"127.0.0.1:{self.server.server_port}"
        return self.headers.get("Host") == expected

    def _send(self, status: int, payload, content_type="application/json"):
        body = (
            payload.encode("utf-8")
            if isinstance(payload, str)
            else json.dumps(payload).encode("utf-8")
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._trusted():
            self._send(403, {"error": "Local origin required"})
        elif self.path in {"/", "/planner"}:
            self._send(
                200,
                files("tori_taurus")
                .joinpath("scanner.html" if self.path == "/" else "beta.html")
                .read_text(encoding="utf-8"),
                "text/html",
            )
        elif self.path == "/api/status":
            self._send(
                200,
                {
                    "version": "0.3.0b1",
                    "credentials_configured": credentials_available(),
                    "webull_configured": webull_credentials_available(),
                    "x_configured": bool(os.environ.get("TORI_X_BEARER_TOKEN", "").strip()),
                    "live_verified": False,
                    "default_mode": "demo",
                },
            )
        else:
            self._send(404, {"error": "Not found"})

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if (
            not self._trusted()
            or self.headers.get("Origin") != origin
            or self.headers.get("Content-Type", "").split(";")[0] != "application/json"
        ):
            self._send(403, {"error": "Same-origin JSON request required"})
            return
        if self.path not in {
            "/api/report",
            "/api/social/connect",
            "/api/social/disconnect",
            "/api/social/scan",
            "/api/scan",
            "/api/webull/connect",
            "/api/webull/account",
            "/api/webull/accounts",
            "/api/webull/select",
        }:
            self._send(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("Invalid request length")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/social/connect":
                token = payload.get("token")
                if not isinstance(token, str) or not 20 <= len(token) <= 2048 or any(
                    c.isspace() or ord(c) < 33 or ord(c) > 126 for c in token
                ):
                    raise ValueError("Invalid token")
                os.environ["TORI_X_BEARER_TOKEN"] = token
                self._send(200, {"configured": True, "verified": False})
            elif self.path == "/api/social/disconnect":
                os.environ.pop("TORI_X_BEARER_TOKEN", None)
                self._send(200, {"configured": False})
            elif self.path == "/api/social/scan":
                from .social import collect, summarize

                symbols = payload.get("symbols")
                now = datetime.now(UTC)
                if not isinstance(symbols, list) or any(not isinstance(s, str) for s in symbols):
                    raise ValueError("Invalid ticker list")
                summarize([], symbols, now, [])
                if payload.get("allow_paid_x") is not True or not os.environ.get(
                    "TORI_X_BEARER_TOKEN", ""
                ).strip():
                    self._send(400, {"error": "Connect X and acknowledge the paid scan first."})
                elif not SOCIAL_SCAN_LOCK.acquire(blocking=False):
                    self._send(409, {"error": "A social scan is already running. Wait for its result."})
                else:
                    try:
                        self._send(200, collect(symbols, now, allow_paid_x=True))
                    finally:
                        SOCIAL_SCAN_LOCK.release()
            elif self.path == "/api/webull/connect":
                for key in ("app_key", "app_secret"):
                    value = payload.get(key)
                    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 512:
                        raise ValueError("Invalid credentials")
                os.environ["WEBULL_APP_KEY"] = payload["app_key"].strip()
                os.environ["WEBULL_APP_SECRET"] = payload["app_secret"].strip()
                # Process memory only. Never echo submitted credentials or provider bodies.
                self._send(200, {"configured": True, "verified": False})
            elif self.path == "/api/webull/accounts":
                from .market_data.webull import WebullProvider

                self._send(200, {"accounts": WebullProvider().list_accounts()})
            elif self.path == "/api/webull/select":
                from .market_data.webull import WebullProvider

                account_id = payload.get("account_id")
                if not isinstance(account_id, str) or account_id not in {
                    a["id"] for a in WebullProvider().list_accounts()
                }:
                    raise ValueError("Invalid account selection")
                os.environ["WEBULL_ACCOUNT_ID"] = account_id
                self._send(200, {"selected": True})
            elif self.path == "/api/webull/account":
                from .market_data.webull import WebullProvider

                self._send(200, WebullProvider().account_snapshot())
            elif self.path == "/api/scan":
                from .scanner.dashboard import scan_payload

                self._send(200, scan_payload(payload))
            else:
                self._send(200, evaluate_payload(payload))
        except MarketDataError as exc:
            self._send(422, {"error": str(exc), "live_verified": False})
        except (ValueError, TypeError, KeyError, ArithmeticError, AttributeError):
            self._send(
                400,
                {
                    "error": (
                        "Check the X token or use 1 to 100 uppercase stock tickers."
                        if self.path.startswith("/api/social/") else
                        "Check scanner price bounds ($0.01 to below $5), minimum gain, "
                        "whole volume, depth (20/40/60), and account risk inputs."
                        if self.path == "/api/scan"
                        else "Check the numeric fields, positive equity/entry, shares, stop below entry, and last-exit date."
                    )
                },
            )
        except (RuntimeError, ImportError, OSError):
            self._send(
                422,
                {
                    "error": "Local data/calendar service unavailable. Use demo or check the local installation.",
                    "live_verified": False,
                },
            )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Launch the local Tori Taurus research beta")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Port must be 1–65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), BetaHandler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{args.port}"
    print(
        f"Tori Taurus beta: {url}\nDemo mode is available. Account form data stays in memory. Ctrl+C stops the server."
    )
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
