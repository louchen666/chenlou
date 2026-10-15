"""Tests for position_sizing.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_core import position_sizing


def test_basic_long():
    r = position_sizing.calculate(account=50000, entry=100, stop=98, risk_pct=1.0)
    # risk = $500, per-share risk = $2, → 250 shares
    assert r["units"] == 250
    assert r["dollar_risk"] == 500.0


def test_target_rr():
    r = position_sizing.calculate(50000, 100, 98, 1.0, target=106)
    # risk = $2, reward = $6 → R:R 3
    assert r["rr"] == 3.0


def test_short():
    r = position_sizing.calculate(50000, 100, 102, 1.0, target=94)
    # risk = $2, reward = $6 → R:R 3
    assert r["units"] == 250
    assert r["rr"] == 3.0


def test_crypto_min_unit():
    # BTC at $70,000 with $50k account, 1% risk, $1000 stop → 0.5 BTC raw
    # min_unit 0.0001 → rounds to 0.5 BTC
    r = position_sizing.calculate(
        account=50000, entry=70000, stop=69000,
        risk_pct=1.0, min_unit=0.0001)
    # risk $500 / per-unit risk $1000 = 0.5 BTC
    assert abs(r["units"] - 0.5) < 0.0001


def test_invalid_zero_risk():
    r = position_sizing.calculate(50000, 100, 100)
    assert "error" in r


def test_kelly_negative_edge_returns_zero():
    # 30% win rate, equal magnitudes → negative kelly
    f = position_sizing.kelly_fraction(0.3, 1.0, 1.0)
    assert f == 0.0


def test_kelly_positive_edge():
    # 60% win, avg win 2, avg loss 1 → kelly = (2*0.6 - 0.4)/2 = 0.4
    # 1/4 Kelly = 0.1
    f = position_sizing.kelly_fraction(0.6, 2.0, 1.0, kelly_multiplier=0.25)
    assert abs(f - 0.1) < 0.001


def test_max_position_pct_caps_low_price():
    # DOT-style: low price, tight stop, 1% risk math wants 99% of account.
    # With 25% cap should trim to 25%.
    r = position_sizing.calculate(
        account=50000, entry=1.243, stop=1.2555,
        risk_pct=1.0, min_unit=1e-5, max_position_pct=25.0,
    )
    assert r["capped"] == True
    assert r["pct_of_account"] <= 25.0 + 0.1
    # Actual dollar risk should be smaller than requested $500
    assert r["dollar_risk"] < 500


def test_max_position_pct_no_cap_when_natural():
    # BTC at high price: 1% risk on $50k = $500. Stop $1000 away → 0.5 BTC
    # Position = $35,000 = 70% of account. With 100% cap (default), no trim.
    r = position_sizing.calculate(
        account=50000, entry=70000, stop=69000,
        risk_pct=1.0, min_unit=1e-5,
        max_position_pct=100.0,
    )
    assert r["capped"] == False
    assert abs(r["units"] - 0.5) < 0.001


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
