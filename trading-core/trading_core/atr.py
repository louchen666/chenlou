"""atr.py — Average True Range. Pure math, asset-agnostic."""
from __future__ import annotations

import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    """True Range from OHLC dataframe. Columns: High, Low, Close (capitalized)."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14, method: str = "sma") -> pd.Series:
    """Average True Range.

    method: 'sma' (simple) or 'ema' (Wilder's smoothing — more responsive).
    """
    tr = true_range(df)
    if method == "ema":
        return tr.ewm(alpha=1 / period, adjust=False).mean()
    return tr.rolling(period).mean()


def atr_stop_long(entry: float, atr_value: float, mult: float = 1.5) -> float:
    return entry - mult * atr_value


def atr_stop_short(entry: float, atr_value: float, mult: float = 1.5) -> float:
    return entry + mult * atr_value
