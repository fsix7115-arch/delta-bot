"""Fetch Delta Exchange India BTCUSD/ETHUSD perpetual candles to CSV.

Public endpoint, no API key required.
Delta returns candles newest-first; we store oldest-first.
"""
import csv
import os
import time
import urllib.request

BASE = "https://api.india.delta.exchange/v2/history/candles"
OUT = os.path.join(os.path.dirname(__file__), "data")

# Delta caps a single candles request; page backwards in chunks.
RESOLUTIONS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
FIELDS = ["timestamp", "open", "high", "low", "close", "volume"]


def fetch(symbol, resolution, start_ts, end_ts):
    url = f"{BASE}?symbol={symbol}&resolution={resolution}&start={start_ts}&end={end_ts}"
    req = urllib.request.Request(url, headers={"User-Agent": "delta-research/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    import json
    return json.loads(body).get("result", [])


def collect(symbol, resolution, years=3):
    step = RESOLUTIONS[resolution] * 1500
    end = int(time.time())
    start = end - int(years * 365.25 * 86400)
    rows, seen = [], set()
    while end > start:
        batch = fetch(symbol, resolution, start, end)
        if not batch:
            end -= step
            time.sleep(0.4)
            continue
        for c in batch:
            ts = c["time"]
            if ts not in seen:
                seen.add(ts)
                rows.append({
                    "timestamp": ts,
                    "open": c["open"], "high": c["high"],
                    "low": c["low"], "close": c["close"],
                    "volume": c.get("volume", 0),
                })
        oldest = min(c["time"] for c in batch)
        print(f"  {symbol} {resolution}: got {len(batch)}, oldest {oldest}, total {len(rows)}")
        if oldest <= start:
            break
        end = oldest - 1
        time.sleep(0.4)
    rows.sort(key=lambda r: r["timestamp"])
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    targets = [("BTCUSD", r) for r in ("15m", "1h", "4h", "1d")] + \
              [("ETHUSD", r) for r in ("15m", "1h", "4h", "1d")]
    for symbol, res in targets:
        path = os.path.join(OUT, f"{symbol}_{res}.csv")
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            print(f"skip {symbol} {res} (exists)")
            continue
        rows = collect(symbol, res, years=3)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"SAVED {path}: {len(rows)} candles")


if __name__ == "__main__":
    main()
