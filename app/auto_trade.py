"""Daily mom_252 + dvol_chg combined factor auto-BUYER (Alpaca paper).

Hard gates (all must pass to be a candidate):
  1. adv20 >= $20M          tradeable liquidity
  2. worst_1d_3d > -7%      no single-day crash in the last 3 sessions (earnings/news)
  3. mom_252_r >= 0.9       top 10% by 12m skip-1m momentum (MAIN signal)
  4. dvol_chg_r >= 0.5      >= median 5d/63d dollar-vol change (CONFIRM signal)
Then sort by mom_252 desc, take top 15.

Regime gate: SPY close > SPY 200d MA -> proceed; else NO buys this run.
Without it, the combined strategy lost -9.6% in 2022 backtest.

BUY-ONLY: never sells. All exits are manual.

Combo chosen 2026-05-26 from YTD-26 + cross-year backtest on features.parquet:
  mom_252 top10% alone:              YTD-26 5d ret +1.67%, t=4.26
  + dvol_chg >= 0.5 (this combo):    YTD-26 5d ret +2.14%, t=4.43
  + dvol_chg >= 0.7:                 YTD-26 5d ret +2.36%, t=4.60 (too narrow)
Cross-year (2024/25/26) the combo adds 0.05-0.5%/5d vs mom alone. 2023 combo
slightly negative (mom dominant regime). 2022 both die -> regime gate handles.
Rank corr(mom_252, dvol_chg) on YTD-26 = +0.077, near-independent diversifier.

SAFE BY DEFAULT: dry-run prints planned trades, places nothing. Pass --live to
actually submit. Logs every run to data/trade_log.jsonl.

Usage:
  python auto_trade.py            # dry run
  python auto_trade.py --live     # live (paper account) submission
"""
import warnings; warnings.filterwarnings("ignore")
import os, sys, json, math, time, datetime as dt, urllib.request, urllib.error, io
import pandas as pd, yfinance as yf

ROOT = os.path.dirname(os.path.abspath(__file__))
def load_env():
    p=os.path.join(ROOT,".env"); env={}
    for line in open(p):
        line=line.strip()
        if line and not line.startswith("#") and "=" in line:
            k,v=line.split("=",1); env[k]=v
    return env
ENV=load_env()
KEY, SEC, BASE = ENV["APCA_API_KEY_ID"], ENV["APCA_API_SECRET_KEY"], ENV["APCA_API_BASE_URL"]
HDR={"APCA-API-KEY-ID":KEY,"APCA-API-SECRET-KEY":SEC,"Content-Type":"application/json"}

LIVE = "--live" in sys.argv
N_STOCKS = 15
CAPITAL_FRACTION = 0.98   # leave 2% slack to absorb fill slippage / margin friction
OPEN_DELAY_MIN = 5        # wait this many minutes after market open before trading (avoid auction)
DATA_BASE = "https://data.alpaca.markets"
PRICE_BUFFER = 1.005      # 0.5% over latest trade so qty*fill stays inside per_dollar budget
MIN_UNIVERSE = 400        # safety: abort if fewer than this many tickers load (yahoo throttle/partial)
                          # without it a partial download shrinks the cross-section and ranks pick junk

def api(method, path, body=None):
    url=BASE+path
    data=json.dumps(body).encode() if body else None
    req=urllib.request.Request(url, data=data, headers=HDR, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else {"_ok": True, "_status": r.status}
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_msg": e.read().decode()}

def latest_price(sym):
    """Latest trade price from Alpaca data API. None on failure -> caller falls back to screen close."""
    try:
        req = urllib.request.Request(
            f"{DATA_BASE}/v2/stocks/{sym}/trades/latest",
            headers={"APCA-API-KEY-ID":KEY,"APCA-API-SECRET-KEY":SEC})
        with urllib.request.urlopen(req, timeout=10) as r:
            return float(json.loads(r.read().decode())["trade"]["p"])
    except Exception:
        return None

def get_sp500():
    """Fetch S&P500 constituents from Wikipedia, cached to data/sp500_cache.json.
    On any fetch failure, fall back to the last successful cache so a Wikipedia
    outage/format change can't crash the live run."""
    cache=os.path.join(ROOT,"data","sp500_cache.json")
    try:
        url="https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        html=urllib.request.urlopen(req,timeout=30).read().decode()
        df=pd.read_html(io.StringIO(html))[0]
        syms=sorted(set(df["Symbol"].str.replace(".","-",regex=False)))
        if len(syms) < MIN_UNIVERSE:
            raise RuntimeError(f"Wikipedia returned only {len(syms)} symbols")
        with open(cache,"w") as f: json.dump(syms,f)
        return syms
    except Exception as e:
        if os.path.exists(cache):
            print(f"get_sp500: live fetch failed ({e}); using cached constituent list")
            return json.load(open(cache))
        raise RuntimeError(f"get_sp500 failed and no cache available: {e}")

def screen(top_n=None):
    """Apply hard gates -> rank by mom_252, take top `top_n` (default N_STOCKS=15).
    Pass top_n=22 from rebalance.py for hysteresis: caller picks top 15 to ENTER,
    held positions stay alive if still in top 22.
    Gates: adv20>=$20M, worst_1d_3d>-7%, mom_252_r>=0.9, dvol_chg_r>=0.5
    """
    if top_n is None: top_n = N_STOCKS
    tickers=get_sp500()
    # need 252 trading + 21 skip + 20 ADV buffer = ~293 trading days ≈ 420 calendar days
    end=dt.date.today()+dt.timedelta(days=1); start=end-dt.timedelta(days=420)
    frames=[]
    B=100
    for i in range(0,len(tickers),B):
        batch=tickers[i:i+B]
        df=yf.download(batch,start=str(start),end=str(end),progress=False,
                       auto_adjust=True,group_by="ticker",threads=True)
        for t in batch:
            try: sub=df[t][["Close","Volume"]].dropna(how="all").copy()
            except Exception: continue
            if len(sub)<260: continue  # need ≥252 days for mom_252
            sub["ticker"]=t; frames.append(sub.reset_index(names="date"))
    px=pd.concat(frames,ignore_index=True); px.columns=[c.lower() for c in px.columns]
    # SAFETY: abort if the download came back thin (yahoo throttle / partial). A shrunken
    # universe distorts the cross-sectional ranks and would pick junk into a live order.
    n_uni = px["ticker"].nunique()
    if n_uni < MIN_UNIVERSE:
        raise RuntimeError(f"screen(): only {n_uni} tickers loaded (need >={MIN_UNIVERSE}); "
                           f"likely a partial yahoo download — refusing to trade on a thin universe.")
    px["date"]=pd.to_datetime(px["date"]); px=px.sort_values(["ticker","date"])
    g=px.groupby("ticker",group_keys=False)
    px["dv"]=px["close"]*px["volume"]
    px["adv20"]=g["dv"].transform(lambda s:s.rolling(20,min_periods=10).mean())
    px["ret1"]=g["close"].transform(lambda s:s.pct_change())
    # skip-1m 12m momentum: price 21d ago / price 252d ago - 1
    px["mom_252"]=g["close"].transform(lambda s: s.shift(21)/s.shift(252) - 1)
    # crash filter: skip stocks with any single day <-7% in trailing 3 sessions (news/earnings)
    # NOTE: 3 *trading days*, not 3 weeks. Renamed from worst_1d_3w to stop the misleading name.
    px["worst_1d_3d"]=g["ret1"].transform(lambda s:s.rolling(3).min())
    # dvol_chg: 5d vs 63d mean dollar-volume — captures fresh money inflow / attention.
    # min_periods MUST match features.py (full windows) to keep backtest/live factor parity.
    px["dvol_5"]=g["dv"].transform(lambda s:s.rolling(5).mean())
    px["dvol_63"]=g["dv"].transform(lambda s:s.rolling(63).mean())
    px["dvol_chg"]=px["dvol_5"]/px["dvol_63"] - 1
    # only completed sessions
    px=px[px["date"].dt.date < dt.date.today()]
    last=px["date"].max()
    # snapshot at last completed date, with cross-sectional ranks for both factors
    snap=px[(px["date"]==last)&(px["adv20"]>=20e6)].dropna(subset=["mom_252","worst_1d_3d","dvol_chg"]).copy()
    snap["mom_252_r"]=snap["mom_252"].rank(pct=True)
    snap["dvol_chg_r"]=snap["dvol_chg"].rank(pct=True)
    # 4 hard gates (must all pass)
    clean=snap[(snap["worst_1d_3d"]>-0.07)
              &(snap["mom_252_r"]>=0.9)
              &(snap["dvol_chg_r"]>=0.5)]
    clean=clean.sort_values("mom_252",ascending=False).head(top_n)
    return last, clean[["ticker","close","mom_252","mom_252_r","dvol_chg","dvol_chg_r"]]

def check_regime():
    """SPY close > SPY 200d MA. Returns (ok: bool, spy_close, spy_200ma)."""
    end=dt.date.today()+dt.timedelta(days=1); start=end-dt.timedelta(days=380)
    df=yf.download("SPY",start=str(start),end=str(end),progress=False,auto_adjust=True)
    if df.empty: raise RuntimeError("SPY download empty")
    closes = df["Close"].iloc[:,0] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
    closes = closes.dropna()
    closes = closes[closes.index.date < dt.date.today()]  # completed sessions only
    if len(closes) < 200:
        raise RuntimeError(f"SPY: only {len(closes)} closing days, need >=200")
    spy_close = float(closes.iloc[-1])
    spy_200ma = float(closes.rolling(200).mean().iloc[-1])
    return spy_close > spy_200ma, spy_close, spy_200ma

def get_positions():
    """Return {symbol: qty} of current positions."""
    res = api("GET","/v2/positions")
    if isinstance(res, dict) and "_error" in res: return {}
    return {p["symbol"]: int(float(p["qty"])) for p in res}

def cancel_open_orders():
    """Cancel any leftover open orders before placing new ones."""
    res = api("GET","/v2/orders?status=open&limit=500")
    if isinstance(res, dict) and "_error" in res: return 0
    n=0
    for o in res:
        api("DELETE", f"/v2/orders/{o['id']}")
        n+=1
    return n

def submit(sym, qty, side):
    return api("POST","/v2/orders",{"symbol":sym,"qty":abs(int(qty)),"side":side,
                                    "type":"market","time_in_force":"day"})

def main():
    acct=api("GET","/v2/account")
    if "_error" in acct:
        print("ACCOUNT ERROR:", acct); return
    equity=float(acct["equity"]); cash=float(acct["cash"])
    clock=api("GET","/v2/clock")
    print(f"=== {dt.datetime.now():%Y-%m-%d %H:%M} {'LIVE' if LIVE else 'DRY-RUN'} (BUY-ONLY) ===")
    print(f"account {acct['account_number']}  equity ${equity:,.0f}  cash ${cash:,.0f}  market_open={clock.get('is_open')}")

    # Regime gate: SPY > 200d MA. Below MA -> skip buys (cash this run).
    regime_ok, spy_close, spy_200ma = check_regime()
    regime_tag = "OK (bull)" if regime_ok else "BEAR — SKIP buys"
    print(f"REGIME  SPY ${spy_close:,.2f}  vs 200d MA ${spy_200ma:,.2f}  ->  {regime_tag}")
    if not regime_ok:
        log={"ts":dt.datetime.now().isoformat(),"mode":"live" if LIVE else "dry",
             "regime":"BEAR","spy_close":spy_close,"spy_200ma":spy_200ma,"buys":[]}
        with open(os.path.join(ROOT,"data","trade_log.jsonl"),"a") as f:
            f.write(json.dumps(log)+"\n")
        return

    asof, picks = screen()
    current = get_positions()
    # new candidates: in top N, not already held
    new_cands = [(r["ticker"], float(r["close"])) for _,r in picks.iterrows()
                 if r["ticker"] not in current]
    print(f"\ndata as of {asof.date()}  | gates: mom_r>=.9 AND dvol_r>=.5 AND worst_1d_3d>-7%")
    print(f"top {len(picks)} (sorted by mom_252):")
    for _,r in picks.iterrows():
        held = " (held)" if r["ticker"] in current else ""
        print(f"  {r['ticker']:<6}  mom_r={r['mom_252_r']:.2f}  dvol_r={r['dvol_chg_r']:.2f}{held}")
    print(f"already held ({len(current)}): {sorted(current.keys())}")
    print(f"new candidates ({len(new_cands)}): {[s for s,_ in new_cands]}\n")

    log={"ts":dt.datetime.now().isoformat(),"mode":"live" if LIVE else "dry",
         "asof":str(asof.date()),"factor":"mom_252+dvol_chg",
         "regime":"OK","spy_close":spy_close,"spy_200ma":spy_200ma,
         "picks":[{"sym":r["ticker"],"mom_r":float(r["mom_252_r"]),"dvol_r":float(r["dvol_chg_r"])}
                  for _,r in picks.iterrows()],
         "current":current,
         "new_candidates":[s for s,_ in new_cands],
         "buys":[]}

    if not new_cands:
        msg = ("nothing to buy — every candidate is already held."
               if len(picks)>0 else
               "nothing to buy — 0 candidates passed the 4 hard gates today.")
        print(msg)
        with open(os.path.join(ROOT,"data","trade_log.jsonl"),"a") as f:
            f.write(json.dumps(log)+"\n")
        return

    budget = cash * CAPITAL_FRACTION
    per_dollar = budget / len(new_cands)
    print(f"budget ${cash:,.0f} x {CAPITAL_FRACTION} = ${budget:,.0f}  |  ${per_dollar:,.0f} / new candidate\n")

    print(f"{'ticker':<7}{'price':>10}{'src':>6}{'qty':>6}{'cost':>12}")
    buys=[]
    for sym, screen_px in new_cands:
        live_px = latest_price(sym)
        price = live_px if live_px else screen_px
        src = "live" if live_px else "screen"
        q = math.floor(per_dollar / (price * PRICE_BUFFER))
        if q >= 1:
            buys.append((sym, q, price))
            print(f"{sym:<7}{price:>10.2f}{src:>6}{q:>6}{q*price:>12,.2f}")
        else:
            print(f"{sym:<7}{price:>10.2f}{src:>6}{0:>6}{'(skip)':>12}")
    est_cost = sum(q*p for _,q,p in buys)
    print(f"\nplan: {len(buys)} buys, est. cost ${est_cost:,.0f}")
    log["buys"] = [{"sym":s,"qty":q} for s,q,_ in buys]

    if LIVE:
        if not clock.get("is_open"):
            print("\nMARKET CLOSED -- not submitting.")
        else:
            try:
                now = pd.Timestamp.now(tz="UTC")
                today_open = pd.Timestamp(dt.date.today().isoformat()+" 13:30", tz="UTC")
                mins_since_open = (now - today_open).total_seconds()/60
                if 0 <= mins_since_open < OPEN_DELAY_MIN:
                    wait_s = int((OPEN_DELAY_MIN - mins_since_open)*60)
                    print(f"only {mins_since_open:.1f}min past open; sleeping {wait_s}s to skip auction")
                    time.sleep(wait_s)
            except Exception as e:
                print(f"open-delay check skipped: {e}")
            cancelled = cancel_open_orders()
            if cancelled: print(f"cancelled {cancelled} stale open orders")
            print("\nsubmitting BUYS...")
            for s,q,_ in buys:
                r=submit(s,q,"buy"); ok="id" in r
                print(f"  BUY  {s} x{q}: {'OK '+r['id'][:8] if ok else 'FAIL '+str(r.get('_msg',r))}")
                log.setdefault("results",[]).append({"sym":s,"side":"buy","qty":q,"ok":ok})
    else:
        print("\n(dry-run: nothing submitted. add --live during market hours)")

    with open(os.path.join(ROOT,"data","trade_log.jsonl"),"a") as f:
        f.write(json.dumps(log)+"\n")

if __name__=="__main__":
    main()
