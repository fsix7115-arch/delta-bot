"""Fetch extended history + real funding rates from Binance public API.

Why: Delta Exchange only serves ~2 years of candles, so we cannot test a
strategy against the 2020 crash or the 2022 bear market. Binance (public,
no key) has 2020-present plus a real funding-rate history, which lets us
(a) lengthen the sample and (b) model funding drag honestly instead of
ignoring it.

BTC/ETH perps on Binance track Delta's BTCUSD/ETHUSD perps closely enough
for strategy research; we still validate the final result on Delta's own
2-year data.
"""
import csv
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "extended")

KLINES = "https://api.binance.com/api/v3/klines"
FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate"

# Binance spot symbols; perps on the futures exchange use the same underlying.
PAIRS = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT"}
RES_MIN = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research/1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:            # transient 5xx / rate limit
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def fetch_klines(pair, interval, start_ms, end_ms):
    step = RES_MIN[interval] * 60 * 1000 * 999
    rows, cursor = [], start_ms
    while cursor < end_ms:
        url = (f"{KLINES}?symbol={pair}&interval={interval}"
               f"&startTime={cursor}&endTime={end_ms}&limit=1000")
        batch = get(url)
        if not batch:
            break
        for k in batch:
            rows.append({"timestamp": int(k[0] // 1000), "open": float(k[1]),
                         "high": float(k[2]), "low": float(k[3]),
                         "close": float(k[4]), "volume": float(k[5])})
        last_open = int(batch[-1][0])
        if last_open <= cursor:
            break
        cursor = last_open + RES_MIN[interval] * 60 * 1000
        time.sleep(0.12)
    return rows


def fetch_funding(pair, start_ms, end_ms):
    """Page backwards from `end_ms` using explicit startTime windows.

    The naive `&startTime=cursor` form returns the OLDEST page rather than
    advancing, so we walk forward in fixed windows instead.
    """
    rows, seen = [], set()
    window = 90 * 86400 * 1000          # 90 days per request
    cursor = start_ms
    while cursor < end_ms:
        hi = min(cursor + window, end_ms)
        url = (f"{FUNDING}?symbol={pair}&startTime={cursor}"
               f"&endTime={hi}&limit=1000")
        batch = get(url)
        if batch:
            for r in batch:
                t = int(r["fundingTime"] // 1000)
                if t not in seen:
                    seen.add(t)
                    rows.append({"time": t, "rate": float(r["fundingRate"])})
        cursor = hi
        time.sleep(0.15)
        print(f"    funding {pair} to {time.strftime('%Y-%m', time.gmtime(cursor/1000))}"
              f" ({len(rows)} rows)")
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    end_ms = int(time.time() * 1000)
    start_ms = int((time.time() - 6 * 365.25 * 86400) * 1000)

    for sym, pair in PAIRS.items():
        for res in ("1h", "4h", "1d"):
            path = os.path.join(OUT, f"{sym}_{res}.csv")
            if os.path.exists(path) and os.path.getsize(path) > 1000:
                print(f"skip {sym} {res} (exists)")
                continue
            rows = fetch_klines(pair, res, start_ms, end_ms)
            rows.sort(key=lambda r: r["timestamp"])
            seen, uniq = set(), []
            for r in rows:
                if r["timestamp"] not in seen:
                    seen.add(r["timestamp"])
                    uniq.append(r)
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["timestamp", "open", "high",
                                                  "low", "close", "volume"])
                w.writeheader()
                w.writerows(uniq)
            d0 = time.strftime("%Y-%m-%d", time.gmtime(uniq[0]["timestamp"]))
            print(f"SAVED {path}: {len(uniq)} candles from {d0}")
    for sym, pair in PAIRS.items():
        path = os.path.join(OUT, f"{sym}_funding.csv")
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            print(f"skip {sym} funding (exists)")
            continue
        rows = fetch_funding(pair, start_ms, end_ms)
        rows.sort(key=lambda r: r["time"])
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["time", "rate"])
            w.writeheader()
            w.writerows(rows)
        d0 = time.strftime("%Y-%m-%d", time.gmtime(rows[0]["time"]))
        print(f"SAVED {path}: {len(rows)} funding rows from {d0}")


if __name__ == "__main__":
    main()
