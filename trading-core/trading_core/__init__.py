"""trading-core — universal math layer shared by stock-bot and crypto-bot.

This module contains ONLY market-agnostic math (sharpe, drawdown, position sizing,
honest friction models, lessons-log writer, stage-upgrade gating). It does NOT
contain any strategy logic, regime thresholds, score formulas, or asset-specific
parameters. Those live inside each bot independently.

Usage from stock-bot or crypto-bot:
    import sys, os
    sys.path.insert(0, os.path.expanduser("~/trading-core"))
    from trading_core import stats, position_sizing, frictions, lessons_log
"""
from . import stats
from . import position_sizing
from . import frictions
from . import atr
from . import lessons_log
from . import stage_upgrade

__all__ = ["stats", "position_sizing", "frictions", "atr", "lessons_log", "stage_upgrade"]
__version__ = "0.1.0"
