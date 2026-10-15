"""Download SP500 constituents + multi-year adjusted daily OHLCV -> data/prices.parquet"""
import warnings, os, time, sys
warnings.filterwarnings("ignore")
import pandas as pd
import yfinance as yf
import urllib.request, io

os.makedirs("data", exist_ok=True)
START = "2015-01-01"   # ~11y: covers 2018 selloff, 2020 covid, 2022 bear, 2023-25 bull (multi-regime)
END   = "2026-05-22"

def get_sp500():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    tables = pd.read_html(io.StringIO(html))
    df = tables[0]
    syms = df["Symbol"].str.replace(".", "-", regex=False).tolist()  # BRK.B -> BRK-B for yahoo
    return sorted(set(syms))

def main():
    tickers = get_sp500()
    print(f"SP500 constituents: {len(tickers)}")
    # download in batches to be polite to yahoo
    all_frames = []
    B = 50
    for i in range(0, len(tickers), B):
        batch = tickers[i:i+B]
        for attempt in range(3):
            try:
                df = yf.download(batch, start=START, end=END, progress=False,
                                 auto_adjust=True, group_by="ticker", threads=True)
                break
            except Exception as e:
                print(f"  batch {i} attempt {attempt} err: {e}; retry")
                time.sleep(5)
        else:
            print(f"  batch {i} FAILED, skip"); continue
        # reshape group_by ticker -> long
        for t in batch:
            try:
                sub = df[t][["Open","High","Low","Close","Volume"]].copy()
            except Exception:
                continue
            sub = sub.dropna(how="all")
            if sub.empty:
                continue
            sub["ticker"] = t
            all_frames.append(sub.reset_index())
        print(f"  done {min(i+B,len(tickers))}/{len(tickers)}  rows so far={sum(len(f) for f in all_frames)}")
        time.sleep(2)
    out = pd.concat(all_frames, ignore_index=True)
    out.columns = [c.lower() for c in out.columns]
    out = out.rename(columns={"index":"date"})
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values(["ticker","date"]).reset_index(drop=True)
    out.to_parquet("data/prices.parquet")
    print(f"SAVED data/prices.parquet  rows={len(out)}  tickers={out.ticker.nunique()}  "
          f"range={out.date.min().date()}..{out.date.max().date()}")

if __name__ == "__main__":
    main()
