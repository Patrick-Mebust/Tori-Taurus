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

- **Market Data Layer** â€” quotes, bars, volume, historical data, and account-aware inputs
- **Momentum Scanner** â€” configurable scans for price, volume, relative volume, gaps, and momentum
- **Catalyst Engine** â€” company news, SEC filings, scheduled events, and catalyst classification
- **Signal Engine** â€” VWAP, EMA, RSI, momentum, support/resistance, and price/volume confirmation
- **Setup Classifier** â€” identify repeatable patterns such as VWAP reclaim, breakout/retest, and first pullback
- **Tori Score** â€” transparent weighted scoring instead of a black-box prediction
- **Risk Engine** â€” position sizing, invalidation, reward/risk, concentration, and daily-loss guardrails
- **FOMO Guard** â€” behavioral checks for chasing, rapid re-entry, averaging down, and overtrading
- **Trading Journal** â€” structured review of entries, exits, thesis changes, and behavioral patterns
- **Backtesting** â€” test setups against historical data before promoting them into live decision support
- **Dashboard** â€” a unified view of candidates, current setups, risk, and post-trade review

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
â”œâ”€â”€ docs/                  # Architecture and design notes
â”œâ”€â”€ src/tori_taurus/
â”‚   â”œâ”€â”€ market_data/       # Market/account data adapters
â”‚   â”œâ”€â”€ scanner/           # Candidate discovery
â”‚   â”œâ”€â”€ catalysts/         # News and filing analysis
â”‚   â”œâ”€â”€ indicators/        # Technical calculations
â”‚   â”œâ”€â”€ setups/            # Setup classification
â”‚   â”œâ”€â”€ scoring/           # Tori Score
â”‚   â”œâ”€â”€ risk/              # Risk and position sizing
â”‚   â”œâ”€â”€ behavior/          # FOMO / behavioral guardrails
â”‚   â”œâ”€â”€ journal/           # Trade journaling
â”‚   â””â”€â”€ backtesting/       # Strategy evaluation
â”œâ”€â”€ tests/
â”œâ”€â”€ notebooks/
â”œâ”€â”€ .env.example
â”œâ”€â”€ pyproject.toml
â””â”€â”€ README.md
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
unknown: no exchange-calendar or holiday inference is implemented.

CSV records always report source=csv and mode=replay, even if the input says live.
`validate_freshness(quote, now=..., max_age=...)` requires live provenance and rejects
stale or future timestamps. Historical records do not need to pass live freshness.
No live API adapter, credential loading, or order execution is implemented yet.
The Phase 1 live/current-data milestone remains open in roadmap issue #1.
