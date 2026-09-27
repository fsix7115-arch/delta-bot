"""Fetch the Alternative.me Crypto Fear & Greed index (free, no key, 2018->now).

Why this and not "news sentiment": for a BACKTEST we need historical
sentiment that was actually knowable at the time. An LLM scoring today's
headlines about 2022 would leak hindsight. A dated, published daily index is
point-in-time clean, so it can be shifted honestly into a signal.

The index is a published composite: volatility 25%, momentum/volume 25%,
social 15%, surveys 15% (paused), dominance 10%, Google Trends 10%.
It is market-wide and BTC-centric, not per-coin.
"""
import csv
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "sentiment")
URL = "https://api.alternative.me/fng/?limit={limit}&format=json"


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research/1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def main():
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "fear_greed.csv")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        print(f"exists, skipping: {path}")
        return
    # limit=0 returns the full archive
    d = get(URL.format(limit=0))
    data = d.get("data") or []
    if not data:
        print("no data returned:", d)
        return
    rows = []
    for x in data:
        rows.append({
            "timestamp": int(x["timestamp"]),
            "value": int(x["value"]),
            "classification": x.get("value_classification", ""),
        })
    rows.sort(key=lambda r: r["timestamp"])
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "value", "classification"])
        w.writeheader()
        w.writerows(rows)
    d0 = time.strftime("%Y-%m-%d", time.gmtime(rows[0]["timestamp"]))
    d1 = time.strftime("%Y-%m-%d", time.gmtime(rows[-1]["timestamp"]))
    print(f"SAVED {path}: {len(rows)} daily readings {d0} -> {d1}")
    print("latest 5:", [(time.strftime('%Y-%m-%d', time.gmtime(r['timestamp'])),
                         r['value'], r['classification']) for r in rows[-5:]])


if __name__ == "__main__":
    main()
