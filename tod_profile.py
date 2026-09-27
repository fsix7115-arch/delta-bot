"""Time-of-day: when does crypto actually move, and when is it worth trading?

The request was to find out when the big players are active, on the theory
that activity means opportunity. This measures it directly on 15m bars rather
than taking the folklore.

Three questions, in order of usefulness:

  1. When are the biggest moves? If there is a time-of-day edge, it shows up
     as a window where the median absolute move is meaningfully larger.
  2. Does that window hold up out of sample? A 2.7-year dataset split in half
     is the only honest way to test a pattern found in the same data.
  3. How large is the move compared to the 0.18% round-trip cost? A window
     where the median move is 0.10% is worse than useless intraday; it is
     negative expectancy by construction.

All times UTC. Delta reports in UTC and the perps settle on UTC boundaries, so
converting to local time would only add a chance to get the offset wrong.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from engine import load

ROUND_TRIP = 0.0018      # 0.05% taker + 0.04% slip, both sides
TOP_N = 6


def profile(df, label):
    d = df.copy()
    d["hour"] = d.index.hour
    d["absret"] = d["close"].pct_change().abs() * 100
    d["range_pct"] = (d["high"] - d["low"]) / d["close"] * 100
    g = d.groupby("hour").agg(
        n=("absret", "size"),
        med_move=("absret", "median"),
        p90_move=("absret", lambda s: s.quantile(0.9)),
        med_range=("range_pct", "median"),
    )
    g = g[g["n"] > 200]
    if g.empty:
        return None
    base = g["med_move"].median()
    g["vs_median"] = g["med_move"] / base
    g["edge"] = g["med_move"] - ROUND_TRIP * 100     # percent, vs fee hurdle
    print(f"\n--- {label}  ({len(d):,} bars, base median move "
          f"{base:.3f}%) ---")
    print(f"{'hour UTC':>9s} {'n':>7s} {'med move':>9s} {'p90':>7s} "
          f"{'med range':>10s} {'vs med':>7s} {'vs fee':>7s}")
    for h, r in g.sort_values("med_move", ascending=False).head(TOP_N).iterrows():
        print(f"{h:>7d}:00 {int(r['n']):>7d} {r['med_move']:>8.3f}% "
              f"{r['p90_move']:>6.3f}% {r['med_range']:>9.3f}% "
              f"{r['vs_median']:>6.2f}x {r['edge']:>+6.3f}%")
    worst = g.sort_values("med_move").head(2)
    print("  weakest hours: " +
          ", ".join(f"{int(h)}:00 ({r['med_move']:.3f}%)" for h, r in worst.iterrows()))
    return g


def oos_check(df, label):
    """Does the best half's best hour still stand out in the second half?"""
    half = len(df) // 2
    a = profile(df.iloc[:half], f"{label}  FIRST half")
    b = profile(df.iloc[half:], f"{label}  SECOND half")
    if a is None or b is None:
        return
    top_a = set(a.sort_values("med_move", ascending=False).head(4).index)
    top_b = set(b.sort_values("med_move", ascending=False).head(4).index)
    overlap = top_a & top_b
    print(f"\n  {label} out-of-sample check:")
    print(f"    best hours in first half : {sorted(top_a)}")
    print(f"    best hours in second half: {sorted(top_b)}")
    print(f"    overlap: {len(overlap)} of 4  {sorted(overlap)}")
    print("    -> the pattern holds" if len(overlap) >= 3 else
          "    -> the pattern does NOT hold out of sample")


def main():
    print("=" * 76)
    print("  WHEN DOES CRYPTO MOVE?  (Delta 15m bars, all times UTC)")
    print("=" * 76)
    print(f"  round-trip cost to beat: {ROUND_TRIP*100:.2f}%")
    print("  'vs fee' above zero means the typical move in that hour")
    print("  is large enough to cover costs.\n")

    for sym in ("BTCUSD", "ETHUSD"):
        df = load(sym, "15m", source="delta")
        if len(df) < 5000:
            print(f"{sym}: insufficient data ({len(df)} bars)")
            continue
        profile(df, f"{sym} full period")
        oos_check(df, sym)

    print("\n" + "=" * 76)
    print("""
WHAT THIS ACTUALLY SHOWS, AND WHAT IT DOES NOT

Movement by hour is a real and well-documented effect. It matters for two
things: exchange infrastructure load, and slippage. It does not by itself
create an edge, because a window where price moves more also means the wrong
side of the trade moves more, and stops get taken out wider.

The test that matters is the 'vs fee' column. If most hours show a negative
value there, then the typical intraday move is smaller than the cost of
trading it, and no amount of picking the right hour fixes that. The 15m sweep
already showed the overall answer was negative; this narrows down whether any
hour is worth the exception.
""")


if __name__ == "__main__":
    main()
