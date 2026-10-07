# Development Roadmap

## Phase 0 — Foundation

- [x] Public GitHub repository
- [x] Professional README
- [x] Architecture document
- [x] Python package layout
- [x] Environment variable template
- [x] Packaging configuration

## Phase 1 — Market Data Core

Goal: create one trustworthy interface for market data.

- [x] Define quote/bar data models
- [x] Define provider interface
- [x] Add first provider adapter (CSV replay)
- [x] Add read-only live provider adapter (Alpaca REST; mocked-response validation)
- [x] Add repeatable read-only quote/history smoke command and offline acceptance tests
- [ ] Verify authenticated real quote/bar responses (local credentials required)
- [x] Normalize aware timestamps to UTC
- [x] Optional NYSE-family calendar classification (holidays, early closes, DST; daily bars unknown)
- [x] Add freshness validation
- [x] Add unit tests

**Milestone:** Given a ticker, Tori can return validated current/historical market data through one interface.

## Phase 2 — Scanner + Indicators

- [x] Under-$5 configurable daily scanner (caller-supplied universe)
- [x] VWAP
- [x] EMA 5 / EMA 9 / EMA 20
- [x] RSI
- [x] ATR
- [x] Daily relative volume against preceding daily-bar baseline
- [x] Intraday relative volume (matched Eastern-time slots; explicit baseline coverage)
- [x] Volume acceleration (adjacent equal-duration bar-window ratio)
- [x] Daily opening gap metric
- [x] Observed session-slice high/low metrics (explicit coverage)

**Milestone:** Tori produces a deterministic feature set for a candidate.

## Phase 3 — Setup State

- [x] VWAP reclaim
- [x] Breakout/retest research rule v1 (frozen seed level; distinct-bar transitions)
- [x] First-pullback research rule v1 (defined impulse/depth/window; synthetic transitions)
- [ ] higher-low continuation
- [x] VWAP extension limit and explicit EXTENDED state
- [ ] Extension rules for other setups
- [x] Explicit confirmation/invalidation for VWAP reclaim
- [ ] Confirmation/invalidation for remaining setups

**Milestone:** Tori can say *what setup is present and why* without relying on an LLM guess.

## Phase 4 — Catalyst Engine

- [ ] Source ingestion
- [ ] timestamping
- [ ] catalyst type taxonomy
- [ ] LLM-assisted summaries
- [ ] materiality classification
- [ ] financing/dilution risk flags

## Phase 5 — Tori Score

- [ ] Define score components
- [ ] Define weights
- [ ] expose component-level explanation
- [ ] calibrate against historical outcomes
- [ ] version score formulas

## Phase 6 — Risk + FOMO Guard

- [ ] dollar-risk calculation
- [ ] account-risk %
- [ ] position sizing
- [ ] concentration warnings
- [ ] cooldown after exit
- [ ] unsupported averaging-down flag
- [ ] chase/extension warning
- [ ] daily loss guardrails

## Phase 7 — Journal

- [ ] structured trade records
- [ ] setup and catalyst snapshots
- [ ] entry/exit events
- [ ] behavioral flags
- [ ] post-trade review
- [ ] statistics by setup

## Phase 8 — Backtesting

- [ ] historical event replay
- [ ] transaction costs/slippage
- [ ] expectancy
- [ ] drawdown
- [ ] MFE/MAE
- [ ] walk-forward validation
- [ ] no look-ahead bias checks

## Phase 9 — Dashboard + Cloud

- [ ] local dashboard
- [ ] API service
- [ ] containerization
- [ ] GitHub Actions CI
- [ ] cloud deployment
- [ ] observability/logging

## Later / optional

- broker-connected paper execution
- event-driven streaming architecture
- portfolio-level risk engine
- ML models trained on Tori's structured feature history

Live autonomous trading is intentionally **not** an early milestone.
