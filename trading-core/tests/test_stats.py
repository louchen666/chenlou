"""Tests for stats.py — pure math, no network."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_core import stats


def test_profit_factor_basic():
    # 3 wins of 1%, 2 losses of 1% → PF = 3/2 = 1.5
    pf = stats.profit_factor([1, 1, 1, -1, -1])
    assert pf == 1.5, f"expected 1.5, got {pf}"


def test_profit_factor_all_wins():
    pf = stats.profit_factor([1, 2, 3])
    assert pf is None  # no losses → undefined


def test_win_rate():
    wr = stats.win_rate([1, 1, -1, -1, 1])
    assert wr == 60.0


def test_max_drawdown():
    # +10%, -10% from peak → 10% drawdown, but compounded
    # 1.0 → 1.1 → 0.99 = -10% from peak
    mdd = stats.max_drawdown([10, -10])
    # 1*(1.1) = 1.1, then 1.1*(0.9) = 0.99, dd from 1.1 = (1.1-0.99)/1.1*100 = 10%
    assert abs(mdd - 10.0) < 0.1


def test_sharpe_zero_var():
    # constant returns → undefined sharpe
    s = stats.sharpe([1, 1, 1, 1, 1])
    assert s is None


def test_sharpe_positive():
    # Steady positive returns, low variance
    s = stats.sharpe([0.1, 0.1, 0.1, 0.2, 0.1, 0.1, 0.2])
    assert s is not None and s > 0


def test_summary_returns_all_fields():
    r = stats.summary([1, -1, 2, -1, 1, 1, -2, 3])
    assert r["n"] == 8
    assert "profit_factor" in r
    assert "sharpe" in r
    assert "max_drawdown" in r


def test_expectancy():
    e = stats.expectancy([1, -1, 1, -1])
    assert e == 0.0


def test_calmar_positive():
    # Slightly positive expectancy, small drawdown
    c = stats.calmar([0.5, -0.2, 0.5, 0.3, -0.1, 0.4], bars_per_year=252)
    assert c is not None


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
