# Tori Taurus local beta 0.2.0b1

## Try it

Requires Python 3.11 or newer. On Windows, extract the entire beta ZIP into a folder and double-click **Launch-Tori.cmd**. First launch installs dependencies using your Internet connection. A local browser opens at http://127.0.0.1:8765. Keep the launcher window open; Ctrl+C stops the server.

On other systems, create a virtual environment, install `pip install -e '.[calendar]'`, then run `tori-beta`. Use `tori-beta --port 8766` if the default port is occupied.

Select **Demo**, enter a ticker and a proposed plan, then click **Analyze my plan**. Every demo ticker uses the same fabricated series at a fixed historical timestamp. These are not ticker prices. Request time and market evaluation time are shown separately.

The screen puts planned dollar loss, account risk, allowable shares, concentration, buying power and stop status before setup states. Changes to inputs invalidate the displayed report. It evaluates daily-loss headroom, time since exit, entry extension and unsupported averaging down. Context is manually entered and unverified. Daily losses mean gross realized losses; wins do not reset the budget. The chase reference is the last supplied intraday close.

## Connect Alpaca locally

Set `ALPACA_API_KEY` and `ALPACA_API_SECRET` in the environment of the process launching Tori. Restart the server after setting them. Never paste keys into chat, source code, reports or GitHub. A `.env` file is not automatically loaded. The application does not collect credentials through its browser form.

Select **Live** and choose IEX or SIP, then use a real ticker and analyze. IEX represents one exchange, not consolidated volume. SIP requires the appropriate Alpaca entitlement. The connection is only marked verified on a successful fresh quote in that response; account access and order execution are not tested. An old quote remains stale even when authentication succeeds.

Daily aggregates exclude today's unfinished daily bar. Intraday bars include completed regular-session intervals only. Premarket, postmarket, closed sessions, holidays, stale bars and sparse/missing intervals may yield unavailable setup states. No live same-time historical volume baseline is collected in this release; relative volume therefore remains unavailable. Timestamp calendar classification does not verify halts, venue status, liquidity or broker eligibility.

## Scope and privacy

- Read-only quote/history retrieval; no order or account APIs.
- Four proposed setup rules: VWAP reclaim, breakout/retest, first pullback and higher-low continuation. Rules have not been backtested for profitability.
- All reports remain research only, regardless of a confirmed setup or supplied-limit result. Stop levels are planning inputs, not verified broker orders. Gaps, fees, slippage, halts and failed fills can exceed planned losses.
- Server binds only to `127.0.0.1`, rejects foreign Host/cross-origin report requests, and suppresses request logging. Inputs stay in process memory. Do not expose this server publicly.
- No automatic report or account persistence. **Download JSON** deliberately saves a report containing account-derived figures; keep that file private.
- No exchange-wide discovery, news/catalyst verification, trading journal, automated broker sync or autonomous trading in this beta.

## Validation boundaries

Automated tests cover deterministic risk/guardrail boundaries, synthetic/mocked providers, malformed inputs, HTTP origin checks, incomplete market data and missing credentials. Browser demo testing and a packaged install are separate checks. Mocked providers never establish authenticated access. Actual Alpaca verification requires locally configured credentials and a successful fresh live quote.
