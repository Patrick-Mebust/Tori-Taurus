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
