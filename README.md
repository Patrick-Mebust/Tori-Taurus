# Tori Taurus

**AI-assisted quantitative trading research and risk-management platform**

Tori Taurus is a modular Python project for researching, scoring, backtesting, and reviewing active equity trading setups. The system is designed to combine deterministic market calculations with AI-assisted analysis while keeping market data, risk rules, and trade decisions auditable.

> **Status:** Early development / portfolio project  
> **Primary focus:** U.S. equities, momentum setups, catalyst-driven trading, risk management, and behavioral trading review.

## Why this project exists

Most "AI trading" products hide their logic behind a score or prediction. Tori Taurus takes the opposite approach:

- **Market data and indicators are calculated deterministically**
- **AI explains and classifies; it does not invent prices or indicators**
- **Risk management is evaluated before trade quality**
- **Every setup should be testable against historical data**
- **Trade decisions and outcomes should be reviewable after the fact**

The project is intended both as a practical trading research tool and as an engineering portfolio demonstrating Python, APIs, data pipelines, quantitative analysis, AI integration, testing, and cloud-ready architecture.

## Planned capabilities

- **Market Data Layer** — quotes, bars, volume, historical data, and account-aware inputs
- **Momentum Scanner** — configurable scans for price, volume, relative volume, gaps, and momentum
- **Catalyst Engine** — company news, SEC filings, scheduled events, and catalyst classification
- **Signal Engine** — VWAP, EMA, RSI, momentum, support/resistance, and price/volume confirmation
- **Setup Classifier** — identify repeatable patterns such as VWAP reclaim, breakout/retest, and first pullback
- **Tori Score** — transparent weighted scoring instead of a black-box prediction
- **Risk Engine** — position sizing, invalidation, reward/risk, concentration, and daily-loss guardrails
- **FOMO Guard** — behavioral checks for chasing, rapid re-entry, averaging down, and overtrading
- **Trading Journal** — structured review of entries, exits, thesis changes, and behavioral patterns
- **Backtesting** — test setups against historical data before promoting them into live decision support
- **Dashboard** — a unified view of candidates, current setups, risk, and post-trade review

## Architecture principles

1. **Deterministic first, AI second**  
   Prices, indicators, risk calculations, and trade state should come from code and source data.

2. **No hidden magic**  
   Scores should expose their components and rationale.

3. **Separate research from execution**  
   Early versions are decision-support tools, not autonomous trading systems.

4. **Protect credentials and private account data**  
   Secrets belong in environment variables and are never committed to source control.

5. **Backtest before trust**  
   A strategy should earn confidence through evidence, not persuasive AI language.

## Project structure

```text
Tori-Taurus/
├── docs/                  # Architecture and design notes
├── src/tori_taurus/
│   ├── market_data/       # Market/account data adapters
│   ├── scanner/           # Candidate discovery
│   ├── catalysts/         # News and filing analysis
│   ├── indicators/        # Technical calculations
│   ├── setups/            # Setup classification
│   ├── scoring/           # Tori Score
│   ├── risk/              # Risk and position sizing
│   ├── behavior/          # FOMO / behavioral guardrails
│   ├── journal/           # Trade journaling
│   └── backtesting/       # Strategy evaluation
├── tests/
├── notebooks/
├── .env.example
├── pyproject.toml
└── README.md
```

## Local development

Requires Python 3.11 or newer. From the repository root:

```sh
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
```

The market-data package now includes validated models, a provider contract,
freshness checks, and a read-only CSV replay adapter. Other modules remain scaffolding. Imports do not connect to a broker or read credentials.
Copy `.env.example` to `.env` only when configuring a future adapter. The template
contains blank credentials; keep real values in your local environment or a
secrets manager. Store private exports under `data/private/` or `exports/`.

## Roadmap

- [x] Initialize repository
- [x] Define project architecture and security boundaries
- [ ] Build market-data abstraction
- [ ] Build first under-$5 momentum scanner
- [ ] Add technical indicators and setup state
- [ ] Add catalyst classification
- [ ] Implement transparent Tori Score
- [ ] Implement risk and FOMO guardrails
- [ ] Add structured trading journal
- [ ] Add historical backtesting
- [ ] Build dashboard
- [ ] Add CI, tests, and deployment workflow

See [docs/architecture.md](docs/architecture.md) for the system design and [docs/roadmap.md](docs/roadmap.md) for implementation phases.

## Safety and scope

Tori Taurus is a research and decision-support project. It does not guarantee profitable trades and should not be treated as personalized financial advice. Automated execution, if ever explored, will be separated from research logic and protected by explicit risk controls.

## Tech direction

**Python Â· REST/WebSocket APIs Â· pandas/polars Â· quantitative indicators Â· backtesting Â· LLM-assisted analysis Â· testing Â· GitHub Actions Â· cloud deployment**

---

Built as an evolving engineering and quantitative research project.

## Market data core (Phase 1 started)

```python
from pathlib import Path
from datetime import datetime, timezone
from tori_taurus.market_data import CsvProvider

provider = CsvProvider(Path("data/private/quotes.csv"), Path("data/private/bars.csv"))
quote = provider.get_quote("AAPL")
bars = provider.get_bars("AAPL", datetime(2026, 10, 1, tzinfo=timezone.utc),
                         datetime(2026, 10, 8, tzinfo=timezone.utc), interval="1d")
```

CSV headers:
- Quotes: `symbol,timestamp,bid,ask`
- Bars: `symbol,timestamp,open,high,low,close,volume,interval`

Timestamps require an explicit timezone and normalize to UTC. Prices use Decimal.
Bars use inclusive start and exclusive end; results sort by timestamp and duplicate
bars are rejected. Supported intervals: 1m, 5m, 15m, 1h, 1d. An optional `session`
column accepts premarket, regular, postmarket, or unknown. Missing sessions remain
unknown unless you opt into the calendar decorator below.

CSV records always report source=csv and mode=replay, even if the input says live.
`validate_freshness(quote, now=..., max_age=...)` requires live provenance and rejects
stale or future timestamps. Historical records do not need to pass live freshness.
A read-only Alpaca REST adapter is implemented below. Authenticated live verification
remains open in roadmap issue #1; calendar classification is available below.

## Alpaca market data

The adapter follows Alpaca's [latest quote](https://docs.alpaca.markets/us/reference/stocklatestquotesingle-1)
and [historical bars](https://docs.alpaca.markets/us/reference/stockbarsingle-1) contracts.
Supply credentials through your local environment; importing the package never loads
credentials or makes requests. The adapter does not read `.env` automatically.

```python
import os
from datetime import datetime, timedelta, timezone
from tori_taurus.market_data import AlpacaProvider, validate_freshness

provider = AlpacaProvider(os.environ["ALPACA_API_KEY"],
                          os.environ["ALPACA_API_SECRET"], feed="iex")
quote = provider.get_quote("AAPL")
validate_freshness(quote, now=datetime.now(timezone.utc), max_age=timedelta(seconds=60))
print(quote)  # market fields only; no credentials
```

The supported feeds are `iex` and `sip`. IEX covers one exchange; it is not a
consolidated market quote or total market volume. SIP access depends on your
Alpaca entitlements. Sources remain explicit (`alpaca:iex` or `alpaca:sip`).
A latest quote has live provenance but must still pass the caller's freshness
policy before use. Historical bars are raw/unadjusted and labeled replay.
Provider timestamps normalize to UTC; session stays unknown unless wrapped with SessionProvider.

Historical retrieval follows all page tokens, sorts bars, rejects duplicates,
and enforces inclusive start/exclusive end. Symbol remapping is disabled (`asof=-`).
The default 100-page cap rejects incomplete results; narrow your range or explicitly
configure `max_pages` when needed. Requests have a finite timeout, disable redirects,
and expose sanitized HTTP/error messages. There are no automatic retries: callers
must decide how to handle rate limits or temporary failures.

Tests use synthetic mocked responses and never contact Alpaca. An authenticated
live smoke test has not been performed. No trading/order endpoints are included.

## Optional session classification

Install `python -m pip install -e ".[dev,calendar]"` to enable the calendar package.
Base imports and market-data adapters do not require this extra.

```python
from tori_taurus.market_data import NyseSessions, SessionProvider

sessions = NyseSessions()
provider_with_sessions = SessionProvider(provider, sessions)
quote = provider_with_sessions.get_quote("AAPL")
print(quote.session)
```

The decorator works with either CSV or Alpaca providers and preserves prices,
timestamps, source/feed labels, and live/replay provenance. Quotes and intraday
bars classify their record timestamps as premarket, regular, postmarket, or closed.
Daily bars remain unknown because a daily aggregate spans multiple hours.

This is an explicit NYSE-family daytime schedule convention, using
[pandas-market-calendars](https://pandas-market-calendars.readthedocs.io/en/latest/usage.html).
It follows Eastern local dates, DST, holidays, special closures, and early-close
pre/open/close/post boundaries. Boundary starts are inclusive and ends exclusive.
For example, November 27, 2026 closes regular trading at 13:00 ET and the extended
schedule at 17:00 ET, consistent with the
[NYSE calendar](https://www.nyse.com/trade/hours-calendars).

A session label describes a record's timestamp; it does not report live market
status, a symbol halt, or whether your broker/feed supports that session. Overnight
trading, other venue calendars, and emergency closures absent from the installed
calendar package are outside this convention. `closed` means outside this schedule.
Update the calendar package as published rules change. Per-instance date schedules
are cached with a bounded 366-day cache and require no network requests.

## Repeatable live smoke check

After installing the package, run:

```sh
tori-market-check AAPL --feed iex --sessions
# Equivalent without the installed command:
python -m tori_taurus.market_data.smoke AAPL --feed iex --sessions
```

Set `ALPACA_API_KEY` and `ALPACA_API_SECRET` in your local environment first.
The command never reads `.env` automatically and never accepts credentials as
command-line arguments. Omit `--sessions` if the optional calendar extra is absent.

Output is a JSON report with a UTC check time, quote source/feed, timestamp, decimal
bid/ask, freshness, and history count/range. The default checks a quote against a
60-second age budget and retrieves the previous seven calendar days of daily bars.
Use `--max-age-seconds` to choose a nonnegative freshness budget and `--history-days`
(1–30) to choose the history window. History must be nonempty, ordered, unique,
inside the requested range, and match the requested ticker and quote source.

Exit codes:
- `0`: live quote passed freshness and historical data passed validation.
- `1`: provider/data failure or quote not current.
- `2`: check not run due to missing credentials or invalid configuration.

A failed stale quote can be normal after market close; it does not pass as live.
The report validates data transport and shape, not price accuracy, historical
completeness, trade suitability, or broker execution. No orders are submitted.

Development verification used synthetic responses. The local command reported
`not_run` because Alpaca environment credentials were absent. Authenticated live
verification remains pending; mocked test success is not a live-data refresh.

## Phase 2: indicators and daily research scanner

```python
from datetime import datetime, timezone
from decimal import Decimal
from tori_taurus.scanner import ScanConfig, scan_daily

config = ScanConfig(max_price=Decimal("5"), min_volume=100000,
                    min_change_percent=Decimal("3"),
                    min_relative_volume=Decimal("2"), volume_lookback=20)
# histories maps normalized tickers to validated chronological daily Bar lists.
results = scan_daily(histories, as_of=datetime.now(timezone.utc), config=config)
candidates = [result for result in results if result["candidate"]]
```

The universe is supplied by the caller; no exchange-wide discovery is performed.
Every result includes reasons, source, data mode, observation time and features.
The upper price bound is exclusive: exactly $5 is outside an under-$5 scan.
Daily relative volume divides the latest observed daily volume by the mean of
exactly `volume_lookback` preceding daily bars, excluding the latest observation.
Missing warm-up or zero denominators produce `None`, never fabricated values.
A required unavailable metric rejects the candidate explicitly.

`ema`, `rsi`, `atr`, and `vwap` are public functions in `tori_taurus.indicators`.
EMA uses an initial period SMA and multiplier 2/(period+1). RSI and ATR use Wilder
smoothing; RSI needs period+1 closes, ATR starts with high-low for the first bar.
A completely flat RSI is defined as 50. EMA 5/9/20, RSI14 and ATR14 appear in
scanner results when sufficiently warmed up. These conventions follow
[StockCharts EMA](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/moving-averages-simple-and-exponential)
and [RSI](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/relative-strength-index-rsi)
calculation descriptions. Initialization/history length can affect values.

VWAP uses volume-weighted (high+low+close)/3, a bar approximation rather than tick
VWAP. It requires one known intraday session on one Eastern date, and returns None
for zero volume. The caller must supply the complete desired session slice;
a partial slice produces VWAP of only the supplied bars. Daily VWAP is rejected.
See the [VWAP calculation reference](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/volume-weighted-average-price-vwap).

All calculations reject duplicate/unordered records and mixed symbols, intervals,
sources or modes. Daily scanner timestamps must not exceed `as_of`. This timestamp
check does not establish historical point-in-time availability or completed daily
bars: callers must provide appropriate data. Split adjustment and feed coverage
must be consistent; IEX volume is single-exchange volume. A partial daily bar cannot
be compared fairly with full-day volume without a time-of-day baseline. Scanner
matches are research candidates; they do not imply fresh prices or a trade signal.
Intraday observed-window metrics are available below.

## Intraday volume and observed session ranges

```python
from datetime import datetime, timezone
from tori_taurus.indicators import session_features

features = session_features(current_session_bars, historical_session_bar_lists,
                            as_of=datetime.now(timezone.utc), min_sessions=5,
                            acceleration_window=3)
```

Supply one chronological, contiguous slice of a known intraday session and a list
of earlier session slices. Timestamps must represent bar starts. A current bar is
eligible only after its full interval has elapsed by `as_of`; partial bars fail.
Inputs must match ticker, interval, source/feed, mode, and session label.

Relative volume compares cumulative volume in the current supplied slice against
the mean volume in exactly those Eastern wall-clock slots in prior sessions.
DST changes UTC offsets, but matching remains by local time. Extra historical
slots are excluded; sessions missing a required slot do not contribute. Duplicate
baseline dates and same-day/future baselines fail. At least `min_sessions` matching
baselines are required; too few or a zero baseline produces None with a reason.

Volume acceleration is the volume sum in the latest N bars divided by the sum in
the immediately preceding N bars (N=`acceleration_window`). These equal-duration
windows are contiguous. Insufficient bars or a zero prior window produces None.
This is a window-volume ratio, not a derivative or an annualized rate.

Output includes observed high/low, volume, bar-based VWAP, comparison-session counts,
source/mode, check time and exact coverage start/end. High/low and VWAP cover only
the supplied slice; callers must fetch the whole intended session before treating
them as full-session metrics. Missing no-trade bars are never invented as zeros.
The function does not validate bars against an exchange calendar or detect halts;
use the calendar decorator for labels and keep feed-coverage limits in view.
All outputs remain research features, with no order execution or entry decision.

## Phase 3: VWAP reclaim research state

```python
from datetime import datetime, timezone
from tori_taurus.setups import ReclaimConfig, evaluate_vwap_reclaim

state = evaluate_vwap_reclaim(completed_session_bars,
                             as_of=datetime.now(timezone.utc), config=ReclaimConfig())
```

Rule version 1.0 processes a supplied contiguous intraday session slice in order.
The first reclaim occurs when the previous close was at/below its cumulative
bar-based VWAP and the next close is strictly above its own cumulative VWAP.
That crossing enters WATCH, not immediate confirmation. The anchor is the lower
low of the preceding and reclaim bars; the reclaim high is the confirmation level.
A later completed close must exceed both that high and current VWAP to confirm.
The default maximum close extension above VWAP is 3%; excessive extension reports
EXTENDED and blocks confirmation until a later bar satisfies the limit.

Any later bar low at/below the anchor, or close strictly below current VWAP,
invalidates first, even if its high also exceeds confirmation. INVALIDATED stays
terminal for this first-reclaim evaluation; no same-slice re-entry is inferred.
Once confirmed, the state holds until invalidation or excessive extension.
Output records trigger/confirmation/invalidation timestamps, levels, source/mode,
coverage, rule version and explicit conditions. The anchor is a research threshold,
not an active broker stop, guaranteed fill, risk budget or position-size decision.

Only completed bars may enter. Latest bar-end age must be within the configurable
observation-age budget (default two minutes); stale data fails explicitly.
The caller must supply the intended session history for meaningful cumulative VWAP.
Partial slices can change results. A zero-volume slice reports UNAVAILABLE.
This is a proposed deterministic rule with synthetic transition tests, not a
backtested strategy or evidence of profitable performance. Breakout/retest,
first-pullback, and higher-low continuation rules remain pending.

## Breakout/retest research state

```python
from datetime import datetime, timezone
from tori_taurus.setups import BreakoutConfig, evaluate_breakout_retest

state = evaluate_breakout_retest(completed_session_bars,
                                as_of=datetime.now(timezone.utc),
                                config=BreakoutConfig(lookback_bars=5))
```

Rule v1.0 freezes resistance at the highest high of the initial `lookback_bars`
(default five). Only subsequent bars can trigger the first breakout: a nonzero-volume
close strictly above resistance. A distinct later bar must retest the level's upper
tolerance band and close at/above resistance while holding above the lower anchor.
A still later nonzero-volume close strictly above the retest high confirms.
The tolerance is 0.5% by default; the anchor is resistance * (1-tolerance/100).
The maximum close extension above resistance is 3% by default.

States are NO_SETUP, WATCH, RETEST, CONFIRMED, EXTENDED, INVALIDATED, or UNAVAILABLE.
After breakout, any later low at/below the anchor or close below resistance
invalidates before retest/confirmation. Invalidation remains terminal for this
first-breakout evaluation. Extension blocks new confirmation, retaining the
breakout/retest timestamps so a later qualifying bar may confirm. Once confirmed,
confirmation holds until invalidation or excessive extension.

Output includes frozen resistance, anchor, confirmation high, transition timestamps,
rule parameters, source/mode and coverage. Seed history never includes the breakout
bar. Lookback selection is a caller-configured convention, not automatic discovery
of an economically meaningful resistance level. Stale or unfinished bars fail;
zero observed volume or insufficient seed/observation history is unavailable.
No active stop or order is created. This proposed rule has synthetic transition
tests and remains unbacktested. First-pullback and higher-low continuation are pending.

## First-pullback research state

`evaluate_first_pullback(bars, as_of=..., config=PullbackConfig())` evaluates one
completed, contiguous, labeled intraday session slice. The default impulse is the
initial three bars with strictly rising closes, nonzero volumes, and at least a
5% gain from first to last close. Unqualified seeds report NO_SETUP; short seeds
report UNAVAILABLE. A qualifying seed enters IMPULSE.

Until the first lower close, the observed impulse peak may grow. The first
nonzero-volume lower close starts WATCH and freezes the peak and first pullback
high. The impulse base is the lowest low in the initial seed. The invalidation
anchor is peak minus 50% (configurable) of the peak-to-base range. Any low at/below
that anchor, including on the first pullback bar, invalidates before confirmation.

A distinct later nonzero-volume close strictly above the first pullback high
confirms, provided it is within the default 3% extension above the frozen peak.
Confirmation must occur within five later bars by default; later observations
report EXPIRED if still unconfirmed. INVALIDATED and EXPIRED are terminal for
this first-event evaluation. EXTENDED blocks new confirmation. Confirmed state
holds until anchor invalidation or excessive extension.

Output includes impulse base/peak, confirmation/anchor levels, transition times,
parameters, source/mode and exact coverage. Stale or unfinished bars fail under
the same two-minute default observation-age policy as other setup rules.
This v1.0 rule is proposed research logic with synthetic transition tests, not a
validated profitable strategy. The anchor is not a broker stop or a position-size
calculation. Higher-low continuation remains pending.

## Higher-low continuation research state

`evaluate_higher_low(bars, as_of=..., config=HigherLowConfig())` processes a completed,
contiguous, labeled intraday session slice chronologically. A strict pivot low
must be lower than each of `pivot_width` bars on both sides (default one). Every
bar in that pivot window must have nonzero volume. Tied lows are not pivots.

A pivot becomes available only after its right-side bars finish. A second
consecutive confirmed pivot must have a strictly higher low and satisfy the
configured minimum percentage improvement (default zero). WATCH begins when
that higher low becomes known. `higher_low_at` identifies the pivot bar start;
`identified_at` is the end of the right-side recognition bar, avoiding backdated
knowledge. A separate later nonzero-volume close strictly above the highest high
between the two pivots confirms within the default 3% extension limit.

The higher-low price is the frozen research invalidation anchor; any subsequent
low at/below it invalidates before confirmation. The intervening high remains
fixed after recognition. Excessive extension reports EXTENDED and blocks new
confirmation. INVALIDATED stays terminal for the first qualifying pair.

Output includes pivot/recognition/transition timestamps, levels, rule version,
parameters, source/mode and coverage. Other transition timestamps identify the
associated completed bar starts; they do not imply that its close was available
at the start. Stale/unfinished input fails. This proposed rule is tested against
synthetic transitions and remains unbacktested; no stop or order is created.

## Structured Tori research report

```sh
tori-report --demo
# Or without reinstalling the command:
python -m tori_taurus.report --demo
```

The demonstration uses fixed synthetic replay data, requires no credentials and
makes no network requests. See `examples/research-report.synthetic.json` for its
reproducible output. This file is an example, not a live broker snapshot.

`build_report(ticker, as_of=..., quote=..., daily_bars=..., session_bars=...,
baseline_sessions=...)` joins validated observations into schema version 1.0.
Output contains quote freshness, daily scan features, intraday metrics, four
separate setup results, and explicit risk/decision availability. Empty optional
inputs report unavailable; mixed ticker/source inputs, future bars and malformed
session slices fail. Daily and session bars may be replay while a quote is live;
provenance remains visible rather than silently relabeled.

For read-only provider retrieval:

```python
from tori_taurus.report import report_from_provider

report = report_from_provider(provider_with_sessions, "AAPL", as_of=as_of,
                              history_start=history_start, session_start=session_start)
```

Use a calendar-labeled provider for intraday retrieval and provide timezone-aware
request dates. The caller controls the intraday slice and must request one session
date. The function fetches a quote, daily history and intraday bars, selecting the
requested known session (regular by default). It does not automatically remove
unfinished bars: invalid slices fail so callers must choose completed-bar boundaries.
For matched-time relative volume, fetch earlier slices and supply them to build_report;
the simple provider helper does not fetch those baseline sessions.

`as_of` is an explicit evaluation clock, not a claim of historical API availability.
Stale session observations can retain descriptive features while setup states are
unavailable. A stale/delayed/replay quote fails the live freshness gate. Reports
always remain RESEARCH_ONLY with ready_to_trade=false; account and stop verification
are outside this planning report. No score or broker order is fabricated. The planning risk calculation is now available below; live account verification remains separate.

## Planning risk: if the trade is wrong, how much can it lose?

```python
from decimal import Decimal
from tori_taurus.risk import RiskInputs, evaluate_risk

plan = RiskInputs(symbol="AAPL", equity=Decimal("1000"), buying_power=Decimal("100"),
                  entry=Decimal("2"), requested_shares=20, stop=Decimal("1.50"),
                  risk_budget_percent=Decimal("1"), max_concentration_percent=Decimal("20"))
risk = evaluate_risk(plan)
# Or: build_report("AAPL", as_of=..., ..., risk_inputs=plan)
```

All account/plan values are user-supplied and unverified. Defaults of 1% budget
and 20% concentration are configurable example policy limits, not recommendations.
The long-share calculator exposes planned incremental and existing dollar loss,
combined average/capital, account-risk percentage, concentration at proposed entry,
buying power before/after, and allowable additional whole shares. It takes the
minimum of risk-budget, buying-power and concentration capacities, rounding down.
Existing gains never offset new downside in the conservative risk-budget test;
combined net loss at the proposed stop is shown separately.

A missing stop blocks sizing and leaves stop-loss/account-risk values unavailable.
Full invested capital is shown separately as capital exposed without a stop.
A stop at/above the proposed long entry is rejected. stop_reported_active is only
an optional user assertion; stop_verified_with_broker always remains false.
A within_supplied_limits result verifies arithmetic against inputs, not execution
readiness. Reports keep ready_to_trade=false and identify unverified risk/stop inputs.

Stop-loss scenarios exclude gaps, slippage, fees and failed fills, and are not a
maximum-loss guarantee. Short positions, options, portfolio-wide correlated risk,
daily-loss limits and behavioral guardrails are not implemented here. An add is
not authorized merely because it fits these limits. No order or stop is placed.

Run `tori-report --demo --with-risk` for synthetic combined report data; see
`examples/research-report.with-risk.synthetic.json`. The example contains no real
account data. Never put private account inputs into committed examples.
