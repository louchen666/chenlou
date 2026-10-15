"""frictions.py — honest paper-trade cost model.

Default to PESSIMISTIC assumptions. Naive paper trading produces PF 30-50%
higher than live; this module is the antidote.

Caller supplies a FrictionProfile per asset class:
  - stock_us:    IBKR Lite / Schwab tier
  - crypto_top5: BTC/ETH/SOL/etc on Binance/Coinbase
  - crypto_alt:  smaller-cap USDT pairs
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class FrictionProfile:
    name: str
    taker_fee_bps: float          # one-way, basis points (1bp = 0.01%)
    maker_fee_bps: float          # one-way
    slippage_bps: float           # one-way, modeled per fill
    latency_ms: int               # signal → order
    partial_fill_prob: float      # 0–1, probability of split fill
    api_downtime_prob: float      # 0–1, % of bars API "fails"
    funding_rate_8h: float | None # perp funding, None for spot
    borrow_rate_annual: float | None  # for shorts, None if N/A


# --- Default profiles, calibrated to public exchange schedules as of 2025-2026 ---

STOCK_US_DAY = FrictionProfile(
    name="stock_us_day",
    taker_fee_bps=0.0,            # IBKR Lite zero-commission for US stocks
    maker_fee_bps=0.0,
    slippage_bps=2.0,             # large-cap day-trade typical
    latency_ms=200,
    partial_fill_prob=0.05,
    api_downtime_prob=0.001,
    funding_rate_8h=None,
    borrow_rate_annual=0.04,      # short borrow rough avg
)

CRYPTO_TOP5_SPOT = FrictionProfile(
    name="crypto_top5_spot",
    taker_fee_bps=10.0,           # Binance 0.10% taker
    maker_fee_bps=10.0,           # Most retail tier
    slippage_bps=5.0,             # BTC/ETH on top exchange
    latency_ms=500,               # geo-distant + WS lag
    partial_fill_prob=0.10,
    api_downtime_prob=0.005,
    funding_rate_8h=None,         # spot, no funding
    borrow_rate_annual=None,
)

CRYPTO_ALT_SPOT = FrictionProfile(
    name="crypto_alt_spot",
    taker_fee_bps=10.0,
    maker_fee_bps=10.0,
    slippage_bps=30.0,            # alt coins much worse
    latency_ms=500,
    partial_fill_prob=0.20,
    api_downtime_prob=0.005,
    funding_rate_8h=None,
    borrow_rate_annual=None,
)

CRYPTO_TOP5_PERP = FrictionProfile(
    name="crypto_top5_perp",
    taker_fee_bps=5.0,            # Binance perp 0.05% taker
    maker_fee_bps=2.0,
    slippage_bps=5.0,
    latency_ms=500,
    partial_fill_prob=0.10,
    api_downtime_prob=0.005,
    funding_rate_8h=0.01,         # rough avg, real bot must use live data
    borrow_rate_annual=None,
)


def apply_entry(price: float, side: str, profile: FrictionProfile,
                rng: random.Random | None = None) -> tuple[float, float]:
    """Return (effective_entry_price, fee_paid_pct) for a market entry.

    Slippage is applied adversely (against the trader) — in real fast markets
    this is the right pessimistic default.
    """
    rng = rng or random
    slip = profile.slippage_bps / 10000
    # Slippage is adverse; longs pay higher, shorts pay lower
    if side == "long":
        eff = price * (1 + slip)
    else:
        eff = price * (1 - slip)
    fee_pct = profile.taker_fee_bps / 10000  # one-way fee as fraction
    return eff, fee_pct


def apply_exit(price: float, side: str, profile: FrictionProfile) -> tuple[float, float]:
    slip = profile.slippage_bps / 10000
    # Exit slippage: long sells lower, short covers higher
    if side == "long":
        eff = price * (1 - slip)
    else:
        eff = price * (1 + slip)
    fee_pct = profile.taker_fee_bps / 10000
    return eff, fee_pct


def round_trip_cost_bps(profile: FrictionProfile) -> float:
    """Total cost in bps for an entry + exit (excluding funding/borrow)."""
    return 2 * profile.slippage_bps + 2 * profile.taker_fee_bps


def funding_cost_pct(profile: FrictionProfile, hours_held: float, side: str = "long") -> float:
    """Perpetual funding cost as % of position value. Long pays positive funding."""
    if profile.funding_rate_8h is None:
        return 0.0
    periods = hours_held / 8.0
    sign = 1 if side == "long" else -1
    return sign * profile.funding_rate_8h * periods


def simulate_partial_fill(target_units: float, profile: FrictionProfile,
                          rng: random.Random | None = None) -> float:
    """Return actual filled units; sometimes less than requested."""
    rng = rng or random
    if rng.random() < profile.partial_fill_prob:
        # Fill 50–95% of target
        return target_units * rng.uniform(0.5, 0.95)
    return target_units


def simulate_api_failure(profile: FrictionProfile,
                         rng: random.Random | None = None) -> bool:
    """Return True if API "failed" this bar; bot must handle gracefully."""
    rng = rng or random
    return rng.random() < profile.api_downtime_prob
