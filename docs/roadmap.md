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
- [ ] Verify authenticated real quote/bar responses
- [x] Normalize aware timestamps to UTC
- [ ] Exchange-calendar session classification (explicit/unknown sessions supported)
- [x] Add freshness validation
- [x] Add unit tests

**Milestone:** Given a ticker, Tori can return validated current/historical market data through one interface.

## Phase 2 — Scanner + Indicators

- [ ] Under-$5 configurable scanner
- [ ] VWAP
- [ ] EMA 5 / EMA 9 / EMA 20
- [ ] RSI
- [ ] ATR
- [ ] Relative volume
- [ ] Volume acceleration
- [ ] Session high/low and gap metrics

**Milestone:** Tori produces a deterministic feature set for a candidate.

## Phase 3 — Setup State

- [ ] VWAP reclaim
- [ ] breakout/retest
- [ ] first pullback
- [ ] higher-low continuation
- [ ] excessive-extension flag
- [ ] explicit confirmation and invalidation

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
