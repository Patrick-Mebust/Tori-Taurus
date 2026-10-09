# Tori Taurus local beta 0.3.0b1 — scanner dashboard

## Try it

Requires Python 3.11 or newer. On Windows, extract the entire beta ZIP into a folder and double-click **Launch-Tori.cmd**. First launch installs dependencies using your Internet connection. A local browser opens at http://127.0.0.1:8765. Keep the launcher window open; Ctrl+C stops the server.

On other systems, create a virtual environment, install `pip install -e '.[calendar,webull]'`, then run `tori-beta`. Use `tori-beta --port 8766` if the default port is occupied.

The home screen opens a demo scanner with four clearly fabricated stocks. Click **Scan for stocks**, then select a candidate to inspect entry, stop, illustrative 2R target and setup rationale. No ticker or entry price is required. The original manual planner remains at `/planner`.

Expand **My account & holdings** once per browser session to enter equity, buying power, limits and optional existing positions. Tori then calculates each candidate's share ceiling, dollar risk, account risk, concentration, remaining buying power, and projected average after an add. Without supplied holdings it labels the calculation a new-position scenario; it does not know your real cost basis. Each candidate uses the same available cash independently and must not be combined as a portfolio allocation. Settings changes invalidate results. Optional auto-refresh starts the next scan 60 seconds after the previous scan completes.

The screen puts planned dollar loss, account risk, allowable shares, concentration, buying power and stop status before setup states. Changes to inputs invalidate the displayed report. The scanner evaluates daily-loss headroom, entry extension and unsupported averaging down. Exit-time cooldown context is available in the secondary manual planner. Context is manually entered and unverified. Daily losses mean gross realized losses; wins do not reset the budget. The chase reference is the last supplied intraday close.

## Connect Webull locally

Use **Connect my Webull account** to enter your API key and secret into the local app, then choose an account. Review [Webull setup, data entitlement and privacy](webull.md). Webull mode reads equity, buying power, holdings and average costs automatically. Confirm realized losses separately before sizing. Keys clear when the server stops.

## Broader scans and stock details

**Scanner filters & depth** controls the minimum price, exclusive price ceiling (at most $5),
minimum positive snapshot gain and minimum snapshot session volume. Select 20, 40 or 60 detailed
candidates. Filters run before the inspection cap on both Webull and Alpaca. The same provider
active/gainer lists supply the universe; this does not turn the scan into exchange-wide discovery.
A 90-second detail budget may leave additional matches uninspected. The coverage summary reports
the applied filters and remaining matches. Demo mode applies the same filters to four synthetic stocks.

Search inspected results by ticker, sort by setup, gain, volume, quoted spread or snapshot price,
or show only stocks with levels, fresh regular-session quotes, or supplied/broker-reported holdings.
These view controls do not make additional data requests or broaden the already completed scan.

The stock detail panel shows bid/ask/spread, snapshot volume, observed intraday range and volume,
VWAP, volume acceleration where available, completed daily EMA 5/9/20, RSI 14, ATR 14, daily opening
gap and completed-day relative volume. All four setup checks show their state and explanation.
Daily features describe the last completed daily bar, not current-session momentum. Intraday
relative volume remains unavailable without matching historical session slices. Missing observations
stay unavailable. Live entry, stop and sizing displays expire when the quote passes 60 seconds;
refreshing the webpage alone does not refresh market observations.

## Watch stocks between scans

Select a candidate and click **Watch this stock**. The watch panel retains up to 50 tickers in
the open tab, with optional setup-change notices after completed scans. The first eligible scan
establishes a baseline; later changes to any of the four setup states produce an in-page notice.
Notices do not place orders, use desktop notifications, or run scans by themselves. Use the existing
scan button or optional refresh control to fetch new observations.

Watched stocks are evaluated only if they appear in the latest inspected results. Missing or stale
observations clear the comparison baseline, rather than suggesting that no change occurred. Changing
data mode/feed resets comparisons and notices so demo and live observations are not mixed. At most
20 notices are retained. Only the watched ticker list is saved in browser session storage and survives page refreshes
in that tab. Closing the tab ends the watchlist session. Baselines and notices reset on refresh;
credentials and broker values are never saved by this feature. When view filters hide every
inspected stock, **Show all inspected stocks** clears those view filters without another data request.

## Connect Alpaca locally

Set `ALPACA_API_KEY` and `ALPACA_API_SECRET` in the environment of the process launching Tori. Restart the server after setting them. Never paste keys into chat, source code, reports or GitHub. A `.env` file is not automatically loaded. The application does not collect credentials through its browser form.

Select **Live Alpaca scan**, choose IEX or SIP, then click **Scan for stocks**. IEX represents one exchange, not consolidated volume. SIP requires the appropriate Alpaca entitlement. Each quote retains its timestamp and freshness result; account access and order execution are not tested. An old quote remains stale even when authentication succeeds.

Daily aggregates exclude today's unfinished daily bar. Intraday bars include completed regular-session intervals only. Premarket, postmarket, closed sessions, holidays, stale bars and sparse/missing intervals may yield unavailable setup states. No live same-time historical volume baseline is collected in this release; relative volume therefore remains unavailable. Timestamp calendar classification does not verify halts, venue status, liquidity or broker eligibility.

## Scope and privacy

- Read-only quote/history retrieval; no order or account APIs.
- Four proposed setup rules: VWAP reclaim, breakout/retest, first pullback and higher-low continuation. Rules have not been backtested for profitability.
- All reports remain research only, regardless of a confirmed setup or supplied-limit result. Stop levels are planning inputs, not verified broker orders. Gaps, fees, slippage, halts and failed fills can exceed planned losses.
- Server binds only to `127.0.0.1`, rejects foreign Host/cross-origin report requests, and suppresses request logging. Inputs stay in process memory. Do not expose this server publicly.
- No automatic report or account persistence. **Download JSON** deliberately saves a report containing account-derived figures; keep that file private.
- No exchange-wide discovery, news/catalyst verification, trading journal, broker order/stop verification or autonomous trading in this beta.

## Validation boundaries

Automated tests cover deterministic risk/guardrail boundaries, synthetic/mocked providers, malformed inputs, HTTP origin checks, incomplete market data and missing credentials. Browser demo testing and a packaged install are separate checks. Mocked providers never establish authenticated access. Actual Alpaca verification requires locally configured credentials and a successful fresh live quote.

## Scanner coverage and conditional prices

Live discovery combines Alpaca's top 100 most-active stocks and top 50 gainers, deduplicates symbols, and filters snapshots to prices from $0.01 to below $5, positive change from the previous daily close, and at least 100,000 shares of day volume. It inspects at most the top 20 matches by snapshot change. This is bounded discovery, not a scan of every stock. Screeners use SIP data; detailed analysis uses the selected feed. Movers retain the prior session before market open. Securities can include ETFs; common-stock type is not verified. See [Alpaca most-actives](https://docs.alpaca.markets/us/reference/mostactives-1) and [movers](https://docs.alpaca.markets/us/reference/movers-1).

The watchlist ranks valid confirmed setups first, then watch setups, then blocked/unavailable results; percent change breaks ties. This is not a probability or profitability score. An entry requires a WATCH or CONFIRMED setup with observed confirmation and invalidation levels. Entry is the greater of ask and confirmation plus a planning increment, rounded upward; stop is below invalidation. The increment is $0.01 above $1, or $0.0001 below $1, and is not exchange tick-size certification. The 2R target is arithmetic, not a forecast.

Live plans require a fresh regular-session quote, a valid positive bid/ask and a spread of at most 2%. Stale, invalid, missing or incomplete observations do not produce prices. Quotes that become stale during a scan lose their plan before the response is returned. One live scan runs at a time; a time budget stops additional candidate requests, with uninspected counts shown. Failed candidates are reported individually. No live news, float, halt validation or intraday historical relative-volume baselines are supplied.
