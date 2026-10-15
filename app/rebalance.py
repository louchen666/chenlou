"""Daily DIFF-mode REBALANCE for the mom_252 + dvol_chg combined strategy.

Sequence:
  1. Regime gate (SPY > 200d MA) — abort if BEAR
  2. screen() — pull top N_HYST_OUT (=22) candidates after gates
  3. Hard stop check (gated by ENABLE_HARD_STOP): any held position down >=15% from
     entry -> force SELL today, blocked from re-buy this run
  4. Hysteresis selection (2026-05-27):
       - ENTER requires top N_STOCKS=15 (entry threshold)
       - HOLD survives if still in top N_HYST_OUT=22 (wider keep band)
       - reduces churn 32% (628->427 sells/yr in backtest) with no alpha loss
  5. Diff vs current positions:
       - SELL = current names dropped out of top 22, OR hit hard stop
       - BUY  = new entries to top 15 not currently held (minus hard-stop names)
       - HOLD = overlap still inside top 22 (no action)
  5. Cancel open orders, submit SELLs, wait until clear (max 60s)
  6. Refresh cash, split equally across BUYs, submit them

Hard stop chosen 2026-05-27 from 1027-episode backtest 2022-2026: -15% from entry
limits worst-case from -32% to -24%, costs only 1.1% of mean return, and barely
touches super-winners (+203% vs +261%) since real winners get +20-50% cushion
before any stop is at risk. Trailing stops were tested and rejected — they cut
super-winner mean from +261% to +27% (kills the alpha).

Compared to full-liquidate-then-rebuy: mom_252 is a slow factor (~80-90% top-15
overlap day-to-day), so diff mode cuts ~80% of churn and keeps the alpha intact.

SAFE BY DEFAULT: dry-run prints the plan, places nothing. Pass --live to execute.

Usage:
  python rebalance.py             # dry run
  python rebalance.py --live      # live (paper account) execution
"""
import warnings; warnings.filterwarnings("ignore")
import os, sys, json, math, time, datetime as dt
import pandas as pd

# reuse helpers from auto_trade
from auto_trade import (api, screen, check_regime, get_positions,
                        cancel_open_orders, submit, latest_price,
                        N_STOCKS, CAPITAL_FRACTION, OPEN_DELAY_MIN, PRICE_BUFFER, ROOT)

LIVE = "--live" in sys.argv
ENABLE_HARD_STOP = False    # 2026-05-27 user chose X-mode (mean-max, no stop). Set True for Y-mode (hard stop -15%).
HARD_STOP_PCT = -0.15       # only used when ENABLE_HARD_STOP=True
N_HYST_OUT = 22             # 2026-05-27 hysteresis: enter requires top 15, hold while still in top N_HYST_OUT.
                            # Backtest 2018-2026: in15/out22 cuts churn 32% (628->427 sells/yr) for NET +41.8% vs strict15 +41.5%.

def get_positions_detailed():
    """Return {sym: {qty, avg_entry, current_px, unrealized_pct}} for all positions."""
    res = api("GET","/v2/positions")
    if isinstance(res, dict) and "_error" in res: return {}
    return {p["symbol"]: {
        "qty": int(float(p["qty"])),
        "avg_entry": float(p["avg_entry_price"]),
        "current_px": float(p["current_price"]),
        "unrealized_pct": float(p["unrealized_plpc"]),
    } for p in res}

def wait_for_sells_clear(sell_syms, timeout_s=60):
    """Poll positions until none of sell_syms is still held, or timeout."""
    sell_set = set(sell_syms)
    t0 = time.time()
    while time.time()-t0 < timeout_s:
        pos = api("GET","/v2/positions")
        if isinstance(pos, list):
            still_held = {p["symbol"] for p in pos} & sell_set
            if not still_held:
                return True
        time.sleep(2)
    return False

def main():
    acct = api("GET","/v2/account")
    if "_error" in acct: print("ACCOUNT ERROR:", acct); return
    clock = api("GET","/v2/clock")
    mode = "LIVE" if LIVE else "DRY-RUN"
    print(f"=== {dt.datetime.now():%Y-%m-%d %H:%M} {mode}  DIFF-REBALANCE ===")
    print(f"account {acct['account_number']}  equity ${float(acct['equity']):,.2f}  "
          f"cash ${float(acct['cash']):,.2f}  market_open={clock.get('is_open')}")

    # Step 1: regime gate
    regime_ok, spy_close, spy_200ma = check_regime()
    tag = "OK (bull)" if regime_ok else "BEAR — REFUSE rebalance"
    print(f"REGIME  SPY ${spy_close:,.2f} vs 200d MA ${spy_200ma:,.2f}  ->  {tag}")
    if not regime_ok:
        print("Aborting: bear regime, refuse to rebalance into long-only book.")
        log = {"ts":dt.datetime.now().isoformat(),"mode":mode.lower(),
               "regime":"BEAR","spy_close":spy_close,"spy_200ma":spy_200ma,"action":"abort"}
        with open(os.path.join(ROOT,"data","trade_log.jsonl"),"a") as f:
            f.write(json.dumps(log)+"\n")
        return

    # Step 2: screen + current (with entry prices). Pull top N_HYST_OUT candidates for hysteresis logic.
    asof, picks = screen(top_n=N_HYST_OUT)
    current_info = get_positions_detailed()
    current = {s: info["qty"] for s, info in current_info.items()}

    # Step 3: hard stop check (gated by ENABLE_HARD_STOP flag)
    hard_stops = {}  # sym -> drawdown_pct
    if ENABLE_HARD_STOP:
        for sym, info in current_info.items():
            if info["avg_entry"] <= 0: continue
            dd = info["current_px"] / info["avg_entry"] - 1
            if dd <= HARD_STOP_PCT:
                hard_stops[sym] = dd

    # Hysteresis selection: enter requires top N_STOCKS, hold survives if still in top N_HYST_OUT.
    candidates = list(picks["ticker"])      # ranked, up to N_HYST_OUT entries
    candidate_rank = {t: i for i, t in enumerate(candidates)}
    top_enter_set = set(candidates[:N_STOCKS])  # the entry-eligible pool (top 15)
    top_hold_set  = set(candidates)             # the keep-alive pool (top N_HYST_OUT=22)

    current_set = set(current.keys())
    stop_set = set(hard_stops.keys())

    # 1. survivors = held & still in top_hold, minus hard stops; ranked by mom for slot priority
    survivors = sorted(
        [t for t in current_set if t in top_hold_set and t not in stop_set],
        key=lambda x: candidate_rank[x]
    )[:N_STOCKS]
    # 2. fill remaining slots from top_enter, excluding survivors and stops
    deficit = N_STOCKS - len(survivors)
    enters = [t for t in candidates[:N_STOCKS]
              if t not in survivors and t not in stop_set][:max(0, deficit)]
    target_set = set(survivors + enters)

    sells_syms = sorted((current_set - target_set) | stop_set)
    buys_syms  = sorted(target_set - current_set)
    holds_syms = sorted(target_set & current_set)

    price_map = {r["ticker"]: float(r["close"]) for _,r in picks.iterrows()}
    rank_map = {r["ticker"]: (float(r["mom_252_r"]), float(r["dvol_chg_r"]))
                for _,r in picks.iterrows()}

    print(f"\ndata as of {asof.date()}  | gates: mom_r>=.9 AND dvol_r>=.5 AND worst_1d_3d>-7%  | hysteresis: enter top {N_STOCKS} / hold top {N_HYST_OUT}{', hard stop -15% from entry' if ENABLE_HARD_STOP else ''}")
    print(f"top {N_HYST_OUT} candidates: {candidates}")
    if hard_stops:
        print(f"\nHARD STOP triggered ({len(hard_stops)}):")
        for sym, dd in hard_stops.items():
            info = current_info[sym]
            print(f"  STOP {sym:<6}  entry ${info['avg_entry']:.2f} -> now ${info['current_px']:.2f}  ({dd*100:+.1f}%)")
    print(f"\nHOLD ({len(holds_syms)}):  {holds_syms}")
    print(f"\nSELL ({len(sells_syms)}):")
    for s in sells_syms:
        reason = f"hard stop {hard_stops[s]*100:+.1f}%" if s in stop_set else f"dropped out of top {N_HYST_OUT}"
        print(f"  SELL {s:<6}  x{current[s]}  ({reason})")
    print(f"\nBUY  ({len(buys_syms)}) — new entries (hard-stopped names blocked today):")
    for s in buys_syms:
        mr, dr = rank_map[s]
        print(f"  BUY  {s:<6}  mom_r={mr:.2f}  dvol_r={dr:.2f}  price=${price_map[s]:.2f}")

    log = {"ts":dt.datetime.now().isoformat(),"mode":mode.lower(),"asof":str(asof.date()),
           "regime":"OK","spy_close":spy_close,"spy_200ma":spy_200ma,
           "candidates":candidates,"target":sorted(target_set),
           "holds":holds_syms,"sells":sells_syms,"buys":buys_syms,
           "hard_stops":{s: hard_stops[s] for s in hard_stops},
           "sells_executed":[],"buys_executed":[]}

    if not sells_syms and not buys_syms:
        print("\nno changes — book already matches today's top 15.")
        with open(os.path.join(ROOT,"data","trade_log.jsonl"),"a") as f:
            f.write(json.dumps(log)+"\n")
        return

    if not LIVE:
        print("\n(dry-run: nothing submitted. Run with --live during market hours.)")
        with open(os.path.join(ROOT,"data","trade_log.jsonl"),"a") as f:
            f.write(json.dumps(log)+"\n")
        return

    # ----- LIVE execution -----
    if not clock.get("is_open"):
        print("\nMARKET CLOSED — aborting LIVE execution.")
        return

    # Wait OPEN_DELAY_MIN past open to skip auction
    try:
        now = pd.Timestamp.now(tz="UTC")
        today_open = pd.Timestamp(dt.date.today().isoformat()+" 13:30", tz="UTC")
        mins_since_open = (now - today_open).total_seconds()/60
        if 0 <= mins_since_open < OPEN_DELAY_MIN:
            wait_s = int((OPEN_DELAY_MIN - mins_since_open)*60)
            print(f"\nonly {mins_since_open:.1f}min past open; sleeping {wait_s}s to skip auction")
            time.sleep(wait_s)
    except Exception as e:
        print(f"open-delay check skipped: {e}")

    cancelled = cancel_open_orders()
    if cancelled: print(f"\ncancelled {cancelled} stale open orders")

    # SELLs first
    if sells_syms:
        print(f"\n--- submitting {len(sells_syms)} SELLs ---")
        for sym in sells_syms:
            qty = current[sym]
            r = submit(sym, qty, "sell"); ok = "id" in r
            oid = r.get("id") if ok else None
            msg = f"OK {oid[:8]}" if ok else f"FAIL {r.get('_msg',r)}"
            print(f"  SELL {sym:<6} x{qty}: {msg}")
            log["sells_executed"].append({"sym":sym,"qty":qty,"ok":ok,"order_id":oid})
        print("\nwaiting for SELLs to clear (up to 60s)...")
        cleared = wait_for_sells_clear(sells_syms, 60)
        print("cleared ✓" if cleared else "WARNING: some sells didn't clear in 60s, continuing anyway")
        time.sleep(2)

    # BUYs sized to TARGET WEIGHT (equity / N_STOCKS), not leftover_cash / n_buys.
    # This is a diff-rebalance: most of the book is HOLD. Splitting freed cash across only
    # the few new entrants would massively overweight them (e.g. 2 buys -> ~16-49% each vs
    # the 6.7% target), wrecking the equal-weight assumption the backtest relies on.
    # Cap by available cash so we never try to spend more than we have.
    if buys_syms:
        acct2 = api("GET","/v2/account")
        cash2 = float(acct2["cash"]); equity2 = float(acct2["equity"])
        target_per = equity2 / N_STOCKS                 # desired $ per name (equal weight)
        budget = cash2 * CAPITAL_FRACTION               # cash actually available this run
        needed = target_per * len(buys_syms)
        if needed <= budget:
            per_dollar = target_per                     # normal case: size to target weight
            note = f"target weight ${target_per:,.2f}/name (equity ${equity2:,.2f}/{N_STOCKS})"
        else:
            per_dollar = budget / len(buys_syms)         # cash-constrained: scale down equally
            note = f"CASH-CONSTRAINED ${per_dollar:,.2f}/name (target ${target_per:,.2f} needs ${needed:,.2f} > budget ${budget:,.2f})"
        print(f"\ncash now: ${cash2:,.2f}  equity ${equity2:,.2f}  | {note}  x {len(buys_syms)}")
        print(f"\n--- submitting {len(buys_syms)} BUYs ---")
        for sym in buys_syms:
            live_px = latest_price(sym)
            price = live_px if live_px else price_map[sym]
            src = "live" if live_px else "screen"
            # buffer above live price so qty*fill_price stays inside per_dollar budget
            q = math.floor(per_dollar / (price * PRICE_BUFFER))
            if q < 1:
                print(f"  {sym:<6} ${price:>8.2f}({src}) x0  (skip — price > per-stock budget)")
                log["buys_executed"].append({"sym":sym,"qty":0,"ok":False,"reason":"price>budget"})
                continue
            res = submit(sym, q, "buy"); ok = "id" in res
            oid = res.get("id") if ok else None
            msg = f"OK {oid[:8]}" if ok else f"FAIL {res.get('_msg',res)}"
            print(f"  BUY  {sym:<6} ${price:>8.2f}({src}) x{q}: {msg}")
            log["buys_executed"].append({"sym":sym,"qty":q,"ok":ok,"order_id":oid,"px":price,"px_src":src})

    with open(os.path.join(ROOT,"data","trade_log.jsonl"),"a") as f:
        f.write(json.dumps(log)+"\n")
    print("\ndiff rebalance complete.")

if __name__=="__main__":
    main()
