"""Shadow mode: run the strategy on live Delta data and report the signal.

Places NO orders. Reads public candles only (no API key needed). Writes every
observation to results/shadow_log.jsonl so performance can be reviewed later.

This exists because the account has no usable capital and no trading scope
yet. Its value is telling us what the strategy does on live prices BEFORE any
money is at risk.
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

import strategies_smc as M

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "results", "shadow_log.jsonl")
BASE = "https://api.india.delta.exchange"
SYMBOL = "ETHUSD"
RESOLUTION = "4h"
PARAMS = dict(impulse_atr=1.0, max_age=30, hold_bars=8)
STOP_PCT = 0.02


def fetch_candles(symbol, resolution, limit_bars=600):
    """Public endpoint, no auth. Delta serves ~2y; we take the recent window."""
    end = int(time.time())
    start = end - limit_bars * 4 * 3600      # 4h bars
    url = (f"{BASE}/v2/history/candles?symbol={symbol}"
           f"&resolution={resolution}&start={start}&end={end}")
    req = urllib.request.Request(url, headers={"User-Agent": "shadow/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    rows = data.get("result", [])
    if not rows:
        raise RuntimeError(f"no candles returned: {data}")
    df = pd.DataFrame([{
        "timestamp": c["time"], "open": c["open"], "high": c["high"],
        "low": c["low"], "close": c["close"], "volume": c.get("volume", 0),
    } for c in rows])
    df["dt"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df = df.set_index("dt").sort_index()
    return df[~df.index.duplicated(keep="first")]


def main():
    df = fetch_candles(SYMBOL, RESOLUTION)
    sig = M.order_block_trade(df, **PARAMS)

    last = sig.iloc[-1]
    state = "LONG" if last > 0 else "SHORT" if last < 0 else "FLAT (no position)"
    price = float(df["close"].iloc[-1])
    bar_time = df.index[-1]

    # how long has the current state been running?
    run_len = 0
    for v in reversed(sig.values):
        if v == last and last != 0:
            run_len += 1
        else:
            break

    n_active = int((sig != 0).sum())
    print("=" * 58)
    print(f"  SHADOW MODE  —  no order is placed")
    print("=" * 58)
    print(f"  pair        : {SYMBOL} {RESOLUTION}")
    print(f"  last bar    : {bar_time}")
    print(f"  price       : {price:,.2f}")
    print(f"  signal      : {state}")
    if last != 0:
        entry = float(df["close"].iloc[-1])
        stop = entry * (1 - STOP_PCT) if last > 0 else entry * (1 + STOP_PCT)
        target = entry * (1 + STOP_PCT * 3) if last > 0 else entry * (1 - STOP_PCT * 3)
        print(f"  if taken now: stop {stop:,.2f} / target {target:,.2f}")
    print(f"  bars in current state : {run_len}")
    print(f"  time in market        : {n_active}/{len(df)} bars "
          f"({n_active/len(df)*100:.0f}%)")
    print("=" * 58)
    print(f"  account: INR 35.01 (~$0.41) — too small for a perp order")
    print(f"  delta min order ~$10; strategy needs ~$8 margin at a 2% stop")
    print("=" * 58)

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "symbol": SYMBOL, "res": RESOLUTION,
            "bar_time": str(bar_time), "price": price,
            "signal": int(last), "bars_in_state": run_len,
            "active_bars": n_active, "total_bars": len(df),
        }) + "\n")
    print(f"  logged -> {LOG}")


if __name__ == "__main__":
    main()
