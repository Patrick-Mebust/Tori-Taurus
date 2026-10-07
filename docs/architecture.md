# Tori Taurus Architecture

## Goal

Build an auditable AI-assisted trading research platform where deterministic code owns market facts and risk calculations, while AI helps interpret catalysts, classify setups, summarize context, and review trading behavior.

## High-level data flow

```text
Market Data / Broker APIs
          |
          v
+----------------------+
|   Market Data Layer  |
+----------------------+
          |
          +------------------+
          |                  |
          v                  v
+----------------+    +----------------+
| Signal Engine  |    | Catalyst Engine|
+----------------+    +----------------+
          |                  |
          +--------+---------+
                   |
                   v
          +----------------+
          | Setup Classifier|
          +----------------+
                   |
                   v
          +----------------+
          |   Tori Score   |
          +----------------+
                   |
          v
+----------------------+      +----------------------+
|     Risk Engine      | ---> | Behavioral Guardrails|
+----------------------+      +----------------------+
          |                         |
          +------------+------------+
                       |
                       v
              +----------------+
              | Decision State |
              +----------------+
                 |          |
                 v          v
          +-----------+  +-----------+
          | Dashboard |  |  Journal  |
          +-----------+  +-----------+
                              |
                              v
                       +-------------+
                       | Backtesting |
                       +-------------+
```

## Component responsibilities

### Market Data Layer

Owns trusted market facts and broker/account adapters.

Responsibilities:
- quotes and OHLCV bars
- historical data
- symbol metadata
- optional account and position context
- normalization across providers
- timestamps and freshness checks

AI must never manufacture values owned by this layer.

### Scanner

Discovers candidate symbols from configurable criteria.

Initial filters may include:
- price range
- percentage move
- absolute and relative volume
- gap percentage
- liquidity
- exchange/listing status
- configurable catalyst presence

The scanner finds candidates; it does not decide that a trade should be taken.

### Catalyst Engine

Collects and classifies time-sensitive context such as:
- company announcements
- SEC filings
- earnings
- financings
- regulatory events
- partnerships/contracts
- corporate actions

AI is appropriate here for summarization and classification, but source documents and timestamps remain authoritative.

### Indicator Engine

Computes deterministic quantitative features such as:
- VWAP
- EMA/SMA
- RSI
- ATR
- rate of change
- volume acceleration
- relative volume
- intraday high/low
- support/resistance candidates

### Setup Classifier

Maps current market state into named, testable setups.

Examples:
- VWAP reclaim
- breakout/retest
- first pullback
- higher-low continuation
- exhaustion/reversal candidate
- halt continuation candidate

Each setup should define:
- required conditions
- confirmation criteria
- invalidation criteria
- optional cooldown rules

### Tori Score

Produces a transparent composite score.

Possible components:
- catalyst quality
- momentum
- liquidity
- technical structure
- extension risk
- dilution/financing risk
- defined-risk quality

The score must expose its component values so it can be debugged and backtested.

### Risk Engine

Evaluates whether a trade idea is structurally acceptable.

Responsibilities:
- planned entry
- invalidation/stop
- dollar risk
- account-risk percentage
- position size
- reward/risk scenarios
- concentration
- daily loss limits
- no-defined-risk state

Risk rules should be deterministic and configurable.

### Behavioral Guardrails

Detects patterns that degrade decision quality, including:
- rapid re-entry after exit
- chasing extended moves
- unsupported averaging down
- escalating size during thesis deterioration
- moving invalidation to avoid realizing a loss
- revenge trading / overtrading patterns

### Journal

Stores structured trade events and post-trade context:
- thesis
- setup
- entry/exit
- risk plan
- catalyst
- score components
- outcome
- behavioral flags
- lessons

### Backtesting

Tests whether a setup has historical evidence before being trusted.

Minimum outputs:
- sample size
- win/loss distribution
- expectancy
- maximum drawdown
- average favorable/adverse excursion
- sensitivity to fees/slippage
- results by market regime where possible

## AI boundary

AI may:
- summarize source material
- classify catalysts
- explain signal combinations
- compare a setup with documented rules
- generate human-readable reviews
- surface behavioral patterns

AI should not:
- invent prices, indicators, positions, or timestamps
- silently alter risk rules
- create a stop solely to make a trade fit a risk budget
- claim certainty about future price movement
- replace historical testing

## Security boundary

Never commit:
- API keys
- access tokens
- account identifiers
- private trading exports
- personally identifying brokerage data

Use environment variables and local/private storage.

## Initial implementation target

The first working vertical slice should be:

**symbol input -> market data -> indicators -> setup state -> risk calculation -> structured Tori output**

This creates a testable core before adding more AI complexity.
