"""Tests for frictions.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_core import frictions


def test_long_entry_slips_up():
    eff, fee = frictions.apply_entry(100, "long", frictions.CRYPTO_TOP5_SPOT)
    # 5bps slippage → 100 * 1.0005 = 100.05
    assert abs(eff - 100.05) < 0.001
    assert abs(fee - 0.0010) < 0.0001


def test_short_entry_slips_down():
    eff, fee = frictions.apply_entry(100, "short", frictions.CRYPTO_TOP5_SPOT)
    # short slippage adverse → fill lower
    assert abs(eff - 99.95) < 0.001


def test_round_trip_cost():
    # Top 5 spot: 5bps slip × 2 + 10bps fee × 2 = 30 bps
    rt = frictions.round_trip_cost_bps(frictions.CRYPTO_TOP5_SPOT)
    assert rt == 30.0


def test_alt_more_expensive():
    rt_alt = frictions.round_trip_cost_bps(frictions.CRYPTO_ALT_SPOT)
    rt_top5 = frictions.round_trip_cost_bps(frictions.CRYPTO_TOP5_SPOT)
    assert rt_alt > rt_top5  # alt slippage 30bps vs top 5bps


def test_funding_cost_none_for_spot():
    cost = frictions.funding_cost_pct(frictions.CRYPTO_TOP5_SPOT, 24, "long")
    assert cost == 0.0


def test_funding_cost_perp_long_pays():
    # 8h funding 0.01% × 3 periods × long = 0.03%
    cost = frictions.funding_cost_pct(frictions.CRYPTO_TOP5_PERP, 24, "long")
    assert abs(cost - 0.03) < 0.001


def test_funding_cost_perp_short_receives():
    cost = frictions.funding_cost_pct(frictions.CRYPTO_TOP5_PERP, 24, "short")
    assert abs(cost - (-0.03)) < 0.001


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
