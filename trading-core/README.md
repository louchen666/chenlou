# trading-core

Universal math layer shared by `stock-bot` and `crypto-bot`.

## Scope (what's in here)

Pure math, market-agnostic:

- **stats.py** — Sharpe, Sortino, max drawdown, profit factor, win rate, expectancy, Calmar
- **position_sizing.py** — fixed-% risk sizing + Kelly criterion
- **atr.py** — Average True Range
- **frictions.py** — honest paper-trade cost model (fees / slippage / latency / partial fills / API downtime / funding rate)
- **lessons_log.py** — append-only markdown lessons log shared by both bots
- **stage_upgrade.py** — paper→live promotion gating with Kelly-calibrated sizing

## Out of scope (does NOT live here)

- Strategy logic (signal rules, entry/exit conditions)
- Asset-specific parameters (thresholds, score weights)
- Regime detection (each bot computes its own)
- Data sources, broker APIs

These stay inside `~/stock-bot/` and `~/crypto-bot/` independently.

## Independence model

| Layer | Shared? |
|---|---|
| A. Code (math primitives) | **Yes** — both bots import from here |
| B. Decisions (params, thresholds, regime) | **No** — each bot calibrates on its own data |
| C. Risk (capital, db, process) | **No** — separate accounts, dbs, processes |

## Usage

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/trading-core"))
from trading_core import stats, position_sizing, frictions, lessons_log, stage_upgrade
```

## Tests

```
~/trading-core/tests/run_all.sh
```

35/35 passing as of Phase 0.
