"""position_sizing.py — risk-based position sizing math.

Universal: works for stocks (shares), crypto (units), forex (lots) — caller
interprets the returned `units` field per their asset.
"""
from __future__ import annotations


def calculate(account: float, entry: float, stop: float,
              risk_pct: float = 1.0, target: float | None = None,
              min_unit: float = 1.0,
              max_position_pct: float = 100.0) -> dict:
    """Compute position size from fixed-% risk per trade.

    Args:
        account: account size in quote currency (USD/USDT)
        entry: entry price
        stop: stop loss price
        risk_pct: % of account at risk (default 1.0)
        target: optional profit target for R:R calculation
        min_unit: minimum tradable unit. Stocks=1 share. Crypto BTC=0.00001.
        max_position_pct: hard cap on position notional as % of account
                         (default 25%). Prevents low-price + tight-stop combos
                         from producing oversized positions even when risk math
                         allows it. Stock-bot caller can pass 100 to disable.

    Returns dict with units (rounded down to min_unit), position_value, R:R.
    Sets `capped: True` when max_position_pct trims the size below risk-implied.
    """
    if entry <= 0 or stop <= 0:
        return {"error": "invalid price"}
    risk_per_unit = abs(entry - stop)
    if risk_per_unit == 0:
        return {"error": "entry == stop"}
    dollar_risk = account * risk_pct / 100
    raw_units = dollar_risk / risk_per_unit

    # Apply max-position-value cap (notional ceiling)
    capped = False
    max_notional = account * max_position_pct / 100
    max_units_from_notional = max_notional / entry if entry > 0 else raw_units
    if raw_units > max_units_from_notional:
        raw_units = max_units_from_notional
        capped = True

    # Round down to nearest min_unit
    if min_unit < 1:
        units = (int(raw_units / min_unit)) * min_unit
    else:
        units = int(raw_units // min_unit) * min_unit
        units = int(units)

    position_value = units * entry
    pct_of_account = position_value / account * 100 if account > 0 else 0
    # Recompute actual dollar_risk (may be lower than requested if capped)
    actual_dollar_risk = units * risk_per_unit

    result = {
        "account": account,
        "entry": entry,
        "stop": stop,
        "risk_pct": risk_pct,
        "risk_per_unit": round(risk_per_unit, 6),
        "dollar_risk": round(actual_dollar_risk, 2),
        "requested_dollar_risk": round(dollar_risk, 2),
        "units": units,
        "position_value": round(position_value, 2),
        "pct_of_account": round(pct_of_account, 2),
        "capped": capped,
    }
    if target:
        rr = (target - entry) / risk_per_unit if entry < target else (entry - target) / risk_per_unit
        result["target"] = target
        result["rr"] = round(rr, 3)
        result["dollar_gain"] = round((target - entry) * units, 2) if entry < target else round((entry - target) * units, 2)
    return result


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float,
                   kelly_multiplier: float = 0.25) -> float:
    """Kelly criterion position sizing fraction.

    win_rate: 0.0–1.0
    avg_win, avg_loss: in % (avg_loss positive number)
    kelly_multiplier: defaults to 1/4 Kelly for safety. Full Kelly = 1.0.

    Returns fraction of account to risk per trade (0.0–1.0).
    """
    if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
        return 0.0
    b = avg_win / avg_loss  # odds ratio
    p = win_rate
    q = 1 - p
    full_kelly = (b * p - q) / b
    if full_kelly <= 0:
        return 0.0
    return max(0.0, full_kelly * kelly_multiplier)
