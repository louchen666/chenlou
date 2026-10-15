"""Tests for atr.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from trading_core import atr


def make_ohlc(closes):
    """Build OHLC df where High = close+1, Low = close-1, no gap."""
    return pd.DataFrame({
        "High": [c + 1 for c in closes],
        "Low": [c - 1 for c in closes],
        "Close": closes,
    })


def test_true_range_basic():
    df = make_ohlc([100, 101, 99, 102, 100])
    tr = atr.true_range(df)
    # First row TR = High - Low = 2 (no prev close)
    # Second row: max(High-Low=2, |H-prev_close|=|102-100|=2, |L-prev_close|=|100-100|=0) = 2
    assert tr.iloc[0] == 2.0
    assert tr.iloc[1] == 2.0


def test_atr_sma():
    closes = [100] * 20
    df = make_ohlc(closes)
    a = atr.atr(df, period=14, method="sma")
    # All TR = 2 → ATR = 2
    assert abs(a.iloc[-1] - 2.0) < 0.01


def test_atr_stop_long_below_entry():
    s = atr.atr_stop_long(entry=100, atr_value=2, mult=1.5)
    assert s == 97.0


def test_atr_stop_short_above_entry():
    s = atr.atr_stop_short(entry=100, atr_value=2, mult=1.5)
    assert s == 103.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as e:
                print(f"  FAIL {name}: {e}")
            except Exception as e:
                print(f"  ERR  {name}: {e}")
