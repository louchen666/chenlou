# Stock Bot

This repository contains the locally found stock-bot code, organized into two components:

- `app/` — S&P 500 factor screening, portfolio rebalancing, sell tracking, data download, and optional Alpaca order execution.
- `trading-core/` — reusable trading calculations for ATR, position sizing, trading frictions, stage upgrades, statistics, and their tests.

## Safety and local setup

Live execution is optional. `app/auto_trade.py` reads Alpaca credentials only from a local `.env` file; no credentials or downloaded market data are included in this repository.

The original local folders were not changed.
