"""Build cross-sectional factor features + forward-return target -> data/features.parquet

Design goal (user's spec): ONE strategy with the SAME parameters that works across many
stocks. So every factor is computed per-stock on its own time series, then ranked
CROSS-SECTIONALLY each day (rank in [0,1]). The model never sees raw prices, only
same-day cross-sectional ranks -> forces a universal rule, not per-ticker curve fitting.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

px = pd.read_parquet("data/prices.parquet")
px = px.sort_values(["ticker","date"])
g = px.groupby("ticker", group_keys=False)

# liquidity filter: need real history + tradeable dollar volume
px["dollar_vol"] = px["close"] * px["volume"]
adv = g["dollar_vol"].transform(lambda s: s.rolling(20, min_periods=10).mean())
px["adv20"] = adv

ret1 = g["close"].transform(lambda s: s.pct_change())
px["ret1"] = ret1

def roll(col, fn, w, minp=None):
    minp = minp or w
    return px.groupby("ticker")[col].transform(lambda s: fn(s, w, minp))

# ---- raw factors (per-stock time series) ----
# momentum at several horizons (skip last 5d to avoid microstructure reversal)
px["mom_21"]  = g["close"].transform(lambda s: s.pct_change(21))
px["mom_63"]  = g["close"].transform(lambda s: s.shift(5) / s.shift(63) - 1)
px["mom_126"] = g["close"].transform(lambda s: s.shift(5) / s.shift(126) - 1)
px["mom_252"] = g["close"].transform(lambda s: s.shift(21) / s.shift(252) - 1)
# short-term reversal
px["rev_5"]   = -g["close"].transform(lambda s: s.pct_change(5))
# volatility (low-vol anomaly)
px["vol_21"]  = g["ret1"].transform(lambda s: s.rolling(21, min_periods=15).std())
px["vol_63"]  = g["ret1"].transform(lambda s: s.rolling(63, min_periods=40).std())
# volume / liquidity dynamics
px["dvol_chg"] = g["dollar_vol"].transform(lambda s: s.rolling(5).mean() / s.rolling(63).mean() - 1)
# distance from highs / range position
px["px_to_252hi"] = g["close"].transform(lambda s: s / s.rolling(252, min_periods=120).max() - 1)
px["px_to_252lo"] = g["close"].transform(lambda s: s / s.rolling(252, min_periods=120).min() - 1)
# gap / overnight tendency
px["hl_range"] = (px["high"] - px["low"]) / px["close"]
px["hl_range_21"] = g["hl_range"].transform(lambda s: s.rolling(21, min_periods=15).mean())
# acceleration: short mom vs long mom
px["mom_accel"] = px["mom_21"] - px["mom_126"]

FACTORS = ["mom_21","mom_63","mom_126","mom_252","rev_5","vol_21","vol_63",
           "dvol_chg","px_to_252hi","px_to_252lo","hl_range_21","mom_accel"]

# ---- target: forward 5-day return (predict next week) ----
px["fwd_ret_5"] = g["close"].transform(lambda s: s.shift(-5) / s - 1)

# liquidity gate: only keep rows with ADV20 >= $20M (tradeable, avoids junk)
px = px[px["adv20"] >= 20e6]

# ---- cross-sectional ranking each day ----
def xs_rank(df, cols):
    # rank within each date -> [0,1]; also build target rank
    out = df.copy()
    for c in cols + ["fwd_ret_5"]:
        out[c + "_r"] = out.groupby("date")[c].rank(pct=True)
    return out

# require min names per day for a meaningful cross-section
day_counts = px.groupby("date")["ticker"].transform("count")
px = px[day_counts >= 30]

px = xs_rank(px, FACTORS)

feat_cols = [c + "_r" for c in FACTORS]
keep = ["date","ticker"] + feat_cols + ["fwd_ret_5","fwd_ret_5_r"]
out = px[keep].dropna(subset=feat_cols + ["fwd_ret_5_r"])
out.to_parquet("data/features.parquet")
print(f"SAVED data/features.parquet rows={len(out)} days={out.date.nunique()} "
      f"tickers={out.ticker.nunique()} factors={len(feat_cols)}")
print("factors:", feat_cols)
