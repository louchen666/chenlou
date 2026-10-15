"""Tests for stage_upgrade.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_core import stage_upgrade


def test_s0_blocks_on_too_few_trades():
    r = stage_upgrade.evaluate_promotion(
        "S0", trades_count=50, observed_pf=1.5,
        days_running=70, max_drawdown_pct=10)
    assert not r["can_promote"]
    assert any("trades" in b for b in r["blockers"])


def test_s0_blocks_on_low_pf():
    r = stage_upgrade.evaluate_promotion(
        "S0", trades_count=300, observed_pf=1.05,
        days_running=70, max_drawdown_pct=10)
    assert not r["can_promote"]


def test_s0_blocks_on_high_dd():
    r = stage_upgrade.evaluate_promotion(
        "S0", trades_count=300, observed_pf=1.30,
        days_running=70, max_drawdown_pct=30)
    assert not r["can_promote"]
    assert any("DD" in b for b in r["blockers"])


def test_s0_promotes_when_all_pass():
    r = stage_upgrade.evaluate_promotion(
        "S0", trades_count=250, observed_pf=1.30,
        days_running=70, max_drawdown_pct=10)
    assert r["can_promote"]
    assert r["next_stage"] == "S1"


def test_s4_terminal():
    r = stage_upgrade.evaluate_promotion(
        "S4", trades_count=10000, observed_pf=2.0,
        days_running=1000, max_drawdown_pct=5)
    assert not r["can_promote"]  # no further stage
    assert r["next_stage"] is None


def test_kelly_blocks_negative_edge():
    r = stage_upgrade.kelly_position_size(
        account=10000, entry=100, stop=99,
        win_rate=0.30, avg_win=1.0, avg_loss=1.0)
    assert "error" in r


def test_kelly_caps_at_stage_pct():
    # huge edge would suggest e.g. 50% but cap at 1%
    r = stage_upgrade.kelly_position_size(
        account=10000, entry=100, stop=99,
        win_rate=0.80, avg_win=3.0, avg_loss=1.0,
        kelly_multiplier=0.25, cap_risk_pct=1.0)
    # account=10000, risk_pct cap=1% → $100 risk, per-unit risk $1 → 100 units
    assert r["units"] == 100


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
