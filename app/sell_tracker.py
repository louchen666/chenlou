"""Sell tracker: classify every Alpaca SELL fill as systematic (rebalance.py) or
manual (user), then track each ticker's price over the following 5/20/60 trading
days to test whether discretionary sells have edge.

Edge test:
- If your manual sells are followed by AVG POSITIVE returns -> you cut winners (no edge)
- If your manual sells are followed by AVG NEGATIVE returns -> you saved losses (edge)
- Need >=5 manual sells before a verdict is meaningful

Usage:
  python sell_tracker.py            # report on last 90 days
  python sell_tracker.py 30         # report on last 30 days
"""
import warnings; warnings.filterwarnings("ignore")
import os, sys, json, datetime as dt
import pandas as pd, yfinance as yf
from auto_trade import api, ROOT

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 90

def load_systematic_order_ids():
    """Read trade_log.jsonl, collect all sell order_ids submitted by rebalance.py."""
    p = os.path.join(ROOT, "data", "trade_log.jsonl")
    ids = set()
    if not os.path.exists(p): return ids
    with open(p) as f:
        for line in f:
            try: rec = json.loads(line)
            except: continue
            for s in rec.get("sells_executed", []):
                if s.get("order_id"): ids.add(s["order_id"])
    return ids

def get_sell_fills(days):
    """Get all filled SELL orders from Alpaca within `days` of today."""
    after_dt = (dt.datetime.utcnow() - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    # Alpaca returns up to 500 per page; paginate by until=
    until = None
    while True:
        path = f"/v2/orders?status=filled&direction=desc&limit=500&after={after_dt}"
        if until: path += f"&until={until}"
        res = api("GET", path)
        if isinstance(res, dict) and "_error" in res: break
        if not res: break
        for o in res:
            if o["side"] != "sell": continue
            if not o.get("filled_avg_price"): continue
            out.append({"id":o["id"],"sym":o["symbol"],
                        "qty":float(o["filled_qty"] or 0),
                        "price":float(o["filled_avg_price"]),
                        "filled_at":o["filled_at"][:19]})
        if len(res) < 500: break
        until = res[-1]["filled_at"]
    return out

def track_followup(sells):
    """For each sell, fetch yfinance close at +5/+20/+60 trading days."""
    if not sells: return {}
    syms = sorted({s["sym"] for s in sells})
    start = (dt.date.today() - dt.timedelta(days=DAYS+10)).isoformat()
    end = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    df = yf.download(syms, start=start, end=end, progress=False,
                     auto_adjust=True, group_by="ticker", threads=True)
    out = {}
    for s in sells:
        sym = s["sym"]; fdate = pd.to_datetime(s["filled_at"]).date()
        try:
            if isinstance(df.columns, pd.MultiIndex):
                ts = df[sym]["Close"].dropna()
            else:
                ts = df["Close"].dropna() if len(syms)==1 else None
            if ts is None or ts.empty: continue
            ts.index = pd.to_datetime(ts.index).date
            sorted_dates = sorted(ts.index)
            after = [d for d in sorted_dates if d > fdate]
            r = {"sym":sym,"sell_date":fdate,"sell_price":s["price"],"qty":s["qty"],
                 "id":s["id"],"mode":s["mode"]}
            for n,label in [(5,"5d"),(20,"20d"),(60,"60d")]:
                if len(after) >= n:
                    fut_px = float(ts[after[n-1]])
                    r[f"px_{label}"] = fut_px
                    r[f"ret_{label}"] = fut_px/s["price"] - 1
                else:
                    r[f"ret_{label}"] = None
            out[(s["id"])] = r
        except Exception as e:
            continue
    return out

def fmt_pct(x): return f"{x*100:+.1f}%" if x is not None else "  --  "
def avg_or_none(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs)/len(xs) if xs else None

def main():
    print(f"=== Sell tracking report (last {DAYS} days) ===\n")
    sys_ids = load_systematic_order_ids()
    sells = get_sell_fills(DAYS)
    if not sells:
        print("No SELL fills in window."); return
    for s in sells: s["mode"] = "sys" if s["id"] in sys_ids else "manual"
    track = track_followup(sells)

    rows = [track[s["id"]] for s in sells if s["id"] in track]
    manual = [r for r in rows if r["mode"]=="manual"]
    systematic = [r for r in rows if r["mode"]=="sys"]
    print(f"Total SELL fills classified: {len(rows)}  (manual={len(manual)}, systematic={len(systematic)})")

    def dump(title, rs):
        if not rs: return
        print(f"\n--- {title} ({len(rs)}) ---")
        print(f"  {'sym':<7}{'sold':<12}{'qty':>5}{'price':>9}{'ret_5d':>9}{'ret_20d':>9}{'ret_60d':>9}")
        for r in sorted(rs, key=lambda x: x["sell_date"]):
            print(f"  {r['sym']:<7}{str(r['sell_date']):<12}{r['qty']:>5.0f}{r['sell_price']:>9.2f}"
                  f"{fmt_pct(r.get('ret_5d')):>9}{fmt_pct(r.get('ret_20d')):>9}{fmt_pct(r.get('ret_60d')):>9}")
        a5 = avg_or_none([r.get("ret_5d") for r in rs])
        a20 = avg_or_none([r.get("ret_20d") for r in rs])
        a60 = avg_or_none([r.get("ret_60d") for r in rs])
        n5 = sum(1 for r in rs if r.get("ret_5d") is not None)
        n20 = sum(1 for r in rs if r.get("ret_20d") is not None)
        n60 = sum(1 for r in rs if r.get("ret_60d") is not None)
        print(f"  avg post-sell ret:  5d={fmt_pct(a5)} (n={n5})  20d={fmt_pct(a20)} (n={n20})  60d={fmt_pct(a60)} (n={n60})")

    dump("MANUAL SELLS (your discretionary stops)", manual)
    dump("SYSTEMATIC SELLS (rebalance.py dropouts)", systematic)

    # Verdict on manual sells
    print(f"\n=== VERDICT (manual sells only) ===")
    valid = [r["ret_20d"] for r in manual if r.get("ret_20d") is not None]
    if len(valid) < 5:
        print(f"  Need >=5 manual sells with 20d follow-up for verdict; currently {len(valid)}.")
        print(f"  Keep going, ask me again in 30 days.")
    else:
        avg = sum(valid)/len(valid)
        if avg > 0.01:
            print(f"  ❌ NO EDGE — your manual sells were followed by avg {fmt_pct(avg)} in 20d.")
            print(f"     You are cutting winners. Consider trusting systematic more.")
        elif avg < -0.01:
            print(f"  ✓ POSSIBLE EDGE — your manual sells were followed by avg {fmt_pct(avg)} in 20d.")
            print(f"     You saved losses. Continue hybrid.")
        else:
            print(f"  NEUTRAL — avg {fmt_pct(avg)} in 20d, close to zero, no clear edge.")
        # Compare to systematic
        valid_s = [r["ret_20d"] for r in systematic if r.get("ret_20d") is not None]
        if len(valid_s) >= 5:
            avg_s = sum(valid_s)/len(valid_s)
            print(f"  (systematic dropouts avg {fmt_pct(avg_s)} in 20d for comparison)")

if __name__=="__main__":
    main()
