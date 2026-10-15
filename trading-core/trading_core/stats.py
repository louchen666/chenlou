"""stats.py — performance statistics shared by stock-bot and crypto-bot.

All functions are pure math on returns (in %, e.g. 1.5 means +1.5%).
No assumptions about asset, market, timeframe, or strategy.

annualization:
  - daily bars: 252 (stock) or 365 (crypto). Caller supplies via bars_per_year.
  - 5min bars: 252 * 78 (stock) or 365 * 288 (crypto).
"""
from __future__ import annotations

import math
from typing import Iterable


def sharpe(returns: list[float], bars_per_year: int = 252,
           risk_free_per_bar: float = 0.0) -> float | None:
    """Annualized Sharpe ratio. returns in %.

    bars_per_year: caller-specific. Stock daily=252, crypto daily=365.
    """
    if len(returns) < 2:
        return None
    avg = sum(returns) / len(returns)
    variance = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return None
    return (avg - risk_free_per_bar) / std * math.sqrt(bars_per_year)


def sortino(returns: list[float], bars_per_year: int = 252,
            target: float = 0.0) -> float | None:
    """Annualized Sortino — only downside vol penalized."""
    if len(returns) < 2:
        return None
    avg = sum(returns) / len(returns)
    downside = [(r - target) ** 2 for r in returns if r < target]
    if not downside:
        return None
    dvar = sum(downside) / len(downside)
    dstd = math.sqrt(dvar)
    if dstd == 0:
        return None
    return (avg - target) / dstd * math.sqrt(bars_per_year)


def max_drawdown(returns: list[float]) -> float:
    """Max peak-to-trough drawdown in %, computed by compounding returns."""
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= (1 + r / 100)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)


def profit_factor(returns: list[float]) -> float | None:
    """Gross win / gross loss. >1 means profitable, <1 means losing."""
    gross_win = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r < 0))
    if gross_loss == 0:
        return None
    return round(gross_win / gross_loss, 3)


def win_rate(returns: list[float]) -> float:
    """% of winning trades."""
    if not returns:
        return 0.0
    wins = sum(1 for r in returns if r > 0)
    return wins / len(returns) * 100


def avg_win_loss(returns: list[float]) -> tuple[float, float]:
    """(avg winner %, avg loser %). avg loser is negative."""
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    avg_w = sum(wins) / len(wins) if wins else 0.0
    avg_l = sum(losses) / len(losses) if losses else 0.0
    return avg_w, avg_l


def expectancy(returns: list[float]) -> float:
    """Expected return per trade in %."""
    if not returns:
        return 0.0
    return sum(returns) / len(returns)


def calmar(returns: list[float], bars_per_year: int = 252) -> float | None:
    """Annualized return / |max drawdown|."""
    if not returns:
        return None
    n = len(returns)
    if n == 0:
        return None
    total = 1.0
    for r in returns:
        total *= (1 + r / 100)
    years = n / bars_per_year
    if years <= 0:
        return None
    annual_return = (total ** (1 / years) - 1) * 100
    mdd = max_drawdown(returns)
    if mdd == 0:
        return None
    return round(annual_return / mdd, 3)


def summary(returns: list[float], bars_per_year: int = 252) -> dict:
    """One-shot dict of all metrics."""
    avg_w, avg_l = avg_win_loss(returns)
    return {
        "n": len(returns),
        "win_rate": round(win_rate(returns), 2),
        "expectancy": round(expectancy(returns), 4),
        "avg_win": round(avg_w, 4),
        "avg_loss": round(avg_l, 4),
        "profit_factor": profit_factor(returns),
        "sharpe": round(s, 3) if (s := sharpe(returns, bars_per_year)) is not None else None,
        "sortino": round(so, 3) if (so := sortino(returns, bars_per_year)) is not None else None,
        "max_drawdown": max_drawdown(returns),
        "calmar": calmar(returns, bars_per_year),
    }
