"""Compare CCXT against the hand-rolled Delta client.

We hand-wrote check_api.py / account_dump.py / fetch_data.py against Delta's
REST docs, which meant hand-maintaining signing, pagination, and the
balance_inr quirk. CCXT already has a maintained Delta adapter, so the
question is whether it saves work or introduces a mismatch.

Three things get checked:
  1. Does it authenticate against the production India endpoint?
  2. Does fetch_balance expose the INR figure, or hide it the way a naive
     client would?
  3. Does its OHLCV match what fetch_data.py produced, bar for bar?

Nothing here places an order. fetch_balance is read-only.
"""
import os
import sys

import ccxt

ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def keys():
    out = {}
    with open(ENV) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def main():
    k = keys()
    key = k.get("DELTA_API_KEY", "")
    secret = k.get("DELTA_API_SECRET", "")
    url = k.get("DELTA_BASE_URL", "https://api.india.delta.exchange")

    # CCXT appends its own path (/v2/public/... or /v2/private/...) to this base,
    # so the base must be the bare host. Passing the full endpoint produces
    # ".../v2/public/v2/assets" and a 404.
    ex = ccxt.delta({
        "apiKey": key,
        "secret": secret,
        "urls": {"api": {
            "public": url,
            "private": url,
        }},
        "enableRateLimit": True,
    })
    print(f"ccxt {ccxt.__version__}  id={ex.id}  name={ex.name}")
    print(f"custom base: {url}\n")

    # 1. public
    try:
        tick = ex.fetch_ticker("BTCUSD")
        print(f"1. public ticker   OK  last={tick.get('last')}  bid={tick.get('bid')}")
    except Exception as e:
        print(f"1. public ticker   FAIL {type(e).__name__} {str(e)[:90]}")

    # 2. auth + INR balance
    # CCXT 4.5.x needs apiKey/secret set on the instance, not just in the
    # constructor dict, when credentials are assigned after construction.
    ex.apiKey = key
    ex.secret = secret
    try:
        bal = ex.fetch_balance()
        total = bal.get("total", {})
        free = bal.get("free", {})
        print(f"2. auth            OK  currencies={len(total)}")
        nz = {c: total[c] for c in total if total[c]}
        print(f"   non-zero totals: {nz if nz else '(none)'}")
        # the trap: is INR present, and is there a raw info copy?
        info = bal.get("info", {})
        keys_seen = set()
        for src in (info, info.get("result", {}) if isinstance(info, dict) else {}):
            if isinstance(src, dict):
                keys_seen |= {k for k in src if "balance" in k.lower()}
        print(f"   balance-ish keys in raw response: {sorted(keys_seen)[:8]}")
    except Exception as e:
        print(f"2. auth            FAIL {type(e).__name__} {str(e)[:90]}")

    # 3. OHLCV parity against our own fetcher
    try:
        from engine import load
        import pandas as pd
        since = int(ccxt.Exchange.parse8601("2026-09-01T00:00:00Z") / 1000)
        ours = load("BTCUSD", "4h", source="delta")
        theirs = pd.DataFrame(ex.fetch_ohlcv("BTCUSD", "4h", since=since, limit=300))
        if len(theirs):
            theirs.columns = ["time", "open", "high", "low", "close", "volume"]
            theirs["time"] = pd.to_datetime(theirs["time"], unit="ms", utc=True)
            ours_idx = pd.to_datetime(ours.index, utc=True)
            joined = theirs.merge(ours.reset_index().rename(columns={"index": "time"}),
                                  on="time", suffixes=("_ccxt", "_ours"))
            print(f"3. ohlcv            {len(joined)} overlapping bars")
            if len(joined):
                d = (joined["close_ccxt"] - joined["close_ours"]).abs()
                print(f"   max close diff: {d.max():.6f}  "
                      f"(0 = identical, tick is 0.5)")
                print(f"   ours last close {joined['close_ours'].iloc[-1]}, "
                      f"ccxt {joined['close_ccxt'].iloc[-1]}")
    except Exception as e:
        print(f"3. ohlcv            FAIL {type(e).__name__} {str(e)[:90]}")

    print("\nverdict: no order endpoint was called")


if __name__ == "__main__":
    main()
