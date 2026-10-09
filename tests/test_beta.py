"""Beta boundaries, including missing credentials and local HTTP isolation."""

import http.client
import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer

import pytest

from tori_taurus import beta
from tori_taurus.behavior.guardrails import GuardrailInputs, evaluate_guardrails
from tori_taurus.market_data import MarketDataError
from tori_taurus.risk import RiskInputs

NOW = datetime(2026, 10, 8, 15, tzinfo=UTC)


def plan(**changes):
    return RiskInputs(
        **(
            {
                "symbol": "TEST",
                "equity": 1000,
                "buying_power": 100,
                "entry": 2,
                "requested_shares": 20,
                "stop": "1.5",
            }
            | changes
        )
    )


def rails(**changes):
    return GuardrailInputs(**({"reference_price": 2} | changes))


def test_daily_loss_boundaries_and_no_win_offset():
    result = evaluate_guardrails(plan(), rails(losses_today=20), as_of=NOW)
    assert result["daily_headroom_after_plan"] == "0.0"
    assert result["status"] == "within_supplied_limits"
    assert (
        "planned_loss_exceeds_daily_headroom"
        in evaluate_guardrails(plan(), rails(losses_today="20.01"), as_of=NOW)["blockers"]
    )
    assert (
        "daily_loss_limit_reached"
        in evaluate_guardrails(plan(requested_shares=0), rails(losses_today=30), as_of=NOW)[
            "blockers"
        ]
    )


def test_cooldown_exact_boundary_and_future_rejected():
    exit_at = NOW - timedelta(minutes=15)
    assert (
        evaluate_guardrails(plan(), rails(last_exit_at=exit_at), as_of=NOW)[
            "cooldown_remaining_seconds"
        ]
        == 0
    )
    result = evaluate_guardrails(
        plan(), rails(last_exit_at=exit_at + timedelta(microseconds=1)), as_of=NOW
    )
    assert result["cooldown_remaining_seconds"] == 1
    assert "exit_cooldown_active" in result["blockers"]
    with pytest.raises(ValueError):
        evaluate_guardrails(plan(), rails(last_exit_at=NOW + timedelta(seconds=1)), as_of=NOW)


def test_chase_threshold_and_averaging_down_are_independent():
    assert (
        "entry_chasing_reference"
        not in evaluate_guardrails(plan(entry="2.06"), rails(), as_of=NOW)["blockers"]
    )
    assert (
        "entry_chasing_reference"
        in evaluate_guardrails(plan(entry="2.0601"), rails(), as_of=NOW)["blockers"]
    )
    p = plan(existing_shares=10, existing_average=3)
    assert "unsupported_averaging_down" in evaluate_guardrails(p, rails(), as_of=NOW)["blockers"]
    assert (
        "unsupported_averaging_down"
        not in evaluate_guardrails(p, rails(thesis_reconfirmed=True), as_of=NOW)["blockers"]
    )
    assert (
        evaluate_guardrails(p, rails(thesis_reconfirmed=True), as_of=NOW)["input_basis"]
        == "user_supplied_unverified_context"
    )


def test_unknown_stop_and_reference_remain_unevaluated():
    result = evaluate_guardrails(plan(stop=None), GuardrailInputs(), as_of=NOW)
    assert result["daily_headroom_after_plan"] is None
    assert result["status"] == "incomplete"
    assert set(result["unevaluated"]) == {
        "daily_planned_loss_without_stop",
        "chase_reference_not_supplied",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"losses_today": -1},
        {"daily_loss_limit_percent": 0},
        {"cooldown_minutes": True},
        {"reference_price": 0},
        {"thesis_reconfirmed": "yes"},
        {"max_chase_percent": "NaN"},
    ],
)
def test_guardrail_inputs_reject_invalid_context(changes):
    with pytest.raises((ValueError, TypeError)):
        rails(**changes)


def test_demo_never_claims_live_or_execution_ready():
    report = beta.evaluate_payload({"ticker": "AAPL", "plan": {"stop": "1.95"}}, now=NOW)
    assert report["symbol"] == "AAPL"
    assert report["quote"]["source"] == "synthetic:beta"
    assert report["beta"]["mode"] == "demo"
    assert not report["beta"]["live_connection_verified"]
    assert report["decision"]["ready_to_trade"] is False
    assert report["guardrails"]["as_of"] == NOW.isoformat()
    assert report["as_of"] != NOW.isoformat()
    assert len(report["beta"]["chart_points"]) == 20
    json.dumps(report)


def test_no_stop_blocks_demo_and_private_inputs_are_not_echoed():
    report = beta.evaluate_payload({"plan": {"unrecognized_secret": "private-sentinel"}}, now=NOW)
    assert report["beta"]["review_status"] == "BLOCKED"
    assert report["risk"]["allowable_add_shares"] == 0
    assert "private-sentinel" not in json.dumps(report)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"mode": "trade"},
        {"ticker": "<script>"},
        {"plan": {"equity": "NaN"}},
        {"plan": {"requested_shares": "1.5"}},
        {"guardrails": {"thesis_reconfirmed": "false"}},
        {"plan": {"stop": "3"}},
        {"plan": {"entry": True}},
    ],
)
def test_invalid_payloads_are_rejected(payload):
    with pytest.raises((ValueError, TypeError)):
        beta.evaluate_payload(payload, now=NOW)


def test_absent_credentials_fail_without_a_network_request(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
    assert not beta.credentials_available()
    with pytest.raises(MarketDataError, match="not configured"):
        beta.fetch_live_data("AAPL", "iex", now=NOW)


@pytest.mark.parametrize("feed", ["iex", "webull"])
def test_live_filters_partial_daily_and_unfinished_intraday(feed):
    clock, quote, daily, current, _ = beta.demo_data("TEST", NOW)

    class Calendar:
        def _bounds(self, day):
            return (
                clock - timedelta(hours=2),
                current[0].timestamp,
                clock + timedelta(hours=4),
                clock + timedelta(hours=8),
            )

    class Provider:
        def get_quote(self, symbol):
            return quote

        def get_bars(self, symbol, start, end, interval):
            return daily + [current[-1]] if interval == "1d" else current

    _, filtered, bars = beta.fetch_live_data(
        "TEST", feed, now=clock - timedelta(seconds=10), provider=Provider(), sessions=Calendar()
    )
    assert len(filtered) == len(daily)
    assert len(bars) == len(current) - 1


def test_sparse_live_slice_does_not_create_setup_claims(monkeypatch):
    _, quote, daily, current, _ = beta.demo_data("TEST", NOW)
    monkeypatch.setattr(
        beta, "fetch_live_data", lambda *args, **kwargs: (quote, daily, current[:3] + current[4:])
    )
    report = beta.evaluate_payload(
        {"mode": "live", "ticker": "TEST", "plan": {"stop": "1.95"}}, now=NOW
    )
    assert report["beta"]["data_quality_warnings"]
    assert report["beta"]["chart_points"] == []
    assert all(s["state"] == "UNAVAILABLE" for s in report["setups"].values())


@pytest.fixture
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), beta.BetaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request(port, method, path, body=None, **headers):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_local_http_serves_ui_and_same_origin_report(local_server):
    status, headers, body = request(local_server, "GET", "/")
    assert status == 200 and b"Tori Taurus" in body
    assert headers["Cache-Control"] == "no-store"
    status, _, body = request(
        local_server,
        "POST",
        "/api/report",
        "{}",
        **{"Origin": f"http://127.0.0.1:{local_server}", "Content-Type": "application/json"},
    )
    assert status == 200 and json.loads(body)["beta"]["mode"] == "demo"


def test_http_rejects_cross_origin_and_foreign_host(local_server):
    assert (
        request(
            local_server,
            "POST",
            "/api/report",
            "{}",
            **{"Origin": "https://evil.example", "Content-Type": "application/json"},
        )[0]
        == 403
    )
    assert request(local_server, "GET", "/", Host="evil.example")[0] == 403


def test_http_invalid_request_does_not_echo_values(local_server):
    body = json.dumps({"plan": {"equity": "private-sentinel"}})
    status, _, response = request(
        local_server,
        "POST",
        "/api/report",
        body,
        **{"Origin": f"http://127.0.0.1:{local_server}", "Content-Type": "application/json"},
    )
    assert status == 400 and b"private-sentinel" not in response


def test_http_missing_credentials_reports_unverified(local_server, monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
    status, _, response = request(
        local_server,
        "POST",
        "/api/report",
        '{"mode":"live"}',
        **{"Origin": f"http://127.0.0.1:{local_server}", "Content-Type": "application/json"},
    )
    assert status == 422 and json.loads(response)["live_verified"] is False


def test_daily_loss_sizing_ceiling_and_active_guardrail_zero():
    result = evaluate_guardrails(plan(requested_shares=2), rails(losses_today=28), as_of=NOW)
    assert result["daily_loss_share_ceiling"] == 4
    assert result["allowable_add_shares_after_guardrails"] == 4
    result = evaluate_guardrails(plan(requested_shares=2), rails(losses_today=30), as_of=NOW)
    assert result["allowable_add_shares_after_guardrails"] == 0


def test_live_connection_requires_fresh_live_quote(monkeypatch):
    from dataclasses import replace

    now = datetime.now(UTC)
    _, quote, daily, _current, _ = beta.demo_data("TEST", now)
    quote = replace(quote, timestamp=now, mode="live")
    monkeypatch.setattr(beta, "fetch_live_data", lambda *args, **kwargs: (quote, daily, []))
    report = beta.evaluate_payload({"mode": "live", "ticker": "TEST"}, now=now)
    assert report["beta"]["live_connection_verified"]
    assert not report["decision"]["ready_to_trade"]
    quote = replace(quote, timestamp=now - timedelta(minutes=10))
    assert not beta.evaluate_payload({"mode": "live", "ticker": "TEST"}, now=now)["beta"][
        "live_connection_verified"
    ]


def test_scanner_endpoint_returns_candidates_without_ticker(local_server):
    status, _, body = request(
        local_server,
        "POST",
        "/api/scan",
        '{"mode":"demo"}',
        **{"Origin": f"http://127.0.0.1:{local_server}", "Content-Type": "application/json"},
    )
    assert status == 200
    result = json.loads(body)
    assert len(result["candidates"]) == 4
    assert result["mode"] == "demo"


def test_root_is_scanner_and_manual_planner_is_secondary(local_server):
    _, _, root = request(local_server, "GET", "/")
    _, _, planner = request(local_server, "GET", "/planner")
    assert b"Candidate watchlist" in root
    assert b"Your trade plan" in planner


def test_social_token_stays_private_and_scan_requires_ack(local_server, monkeypatch):
    monkeypatch.delenv("TORI_X_BEARER_TOKEN", raising=False)
    headers = {"Origin": f"http://127.0.0.1:{local_server}", "Content-Type": "application/json"}
    token = "synthetic-private-token-only"
    status, _, body = request(local_server, "POST", "/api/social/connect",
                              json.dumps({"token": token}), **headers)
    assert status == 200 and token.encode() not in body
    _, _, body = request(local_server, "GET", "/api/status")
    assert json.loads(body)["x_configured"] is True and token.encode() not in body
    calls = []
    monkeypatch.setattr("tori_taurus.social.collect", lambda *a, **k: calls.append(a) or {
        "schema": "tori.social.v1", "tickers": [], "coverage": []})
    for ack in (False, "true", 1):
        assert request(local_server, "POST", "/api/social/scan",
                       json.dumps({"symbols": ["XYZ"], "allow_paid_x": ack}), **headers)[0] == 400
    assert not calls
    assert request(local_server, "POST", "/api/social/scan",
                   json.dumps({"symbols": ["XYZ"], "allow_paid_x": True}), **headers)[0] == 200
    assert len(calls) == 1
    assert request(local_server, "POST", "/api/social/disconnect", "{}", **headers)[0] == 200
    assert request(local_server, "POST", "/api/social/scan",
                   json.dumps({"symbols": ["XYZ"], "allow_paid_x": True}), **headers)[0] == 400


def test_social_rejects_foreign_origin_invalid_tokens_and_busy_scan(local_server, monkeypatch):
    headers = {"Origin": f"http://127.0.0.1:{local_server}", "Content-Type": "application/json"}
    assert request(local_server, "POST", "/api/social/connect", "{}",
                   **{**headers, "Origin": "https://evil.example"})[0] == 403
    for token in ("private-sentinel", "x" * 2100, "invalid token contains spaces"):
        status, _, body = request(local_server, "POST", "/api/social/connect",
                                  json.dumps({"token": token}), **headers)
        assert status == 400 and token.encode() not in body
    monkeypatch.setenv("TORI_X_BEARER_TOKEN", "synthetic-test-token")
    beta.SOCIAL_SCAN_LOCK.acquire()
    try:
        assert request(local_server, "POST", "/api/social/scan",
                       json.dumps({"symbols": ["XYZ"], "allow_paid_x": True}), **headers)[0] == 409
    finally:
        beta.SOCIAL_SCAN_LOCK.release()
