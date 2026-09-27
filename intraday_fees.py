"""Intraday viability: the fee arithmetic, measured rather than asserted.

Earlier rounds dismissed intraday on reasoning alone ("fees eat it"). That is
a guess, and this project has already been wrong four times by asserting
instead of measuring. So: measure it.

The dataset is better than expected -- about 1000 days of continuous 15m bars
per symbol on Delta, which is enough to answer the question properly.

The arithmetic under test, per round trip on Delta perps:

    taker fee 0.05% per side  ->  0.10% round trip
    slippage 0.04% per side   ->  0.08% round trip
    total friction             =  0.18%

A strategy therefore needs to capture MORE than 0.18% per trade just to
breakeven, and substantially more than that to survive a drawdown. The
question is what intraday structure can actually deliver that, and how it
compares to the same strategy on a slower timeframe where the same friction is
amortised over a much larger move.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TAKER = 0.0005
SLIP = 0.0004
ROUND_TRIP = (TAKER + SLIP) * 2 * 100      # percent


def fees():
    print("=" * 72)
    print("  INTRADAY FEE ARITHMETIC  (Delta perps, taker, no VIP tier)")
    print("=" * 72)
    print(f"  taker fee per side   {TAKER*100:6.3f}%")
    print(f"  slippage per side    {SLIP*100:6.3f}%")
    print(f"  ROUND TRIP FRICTION  {ROUND_TRIP:6.3f}%")
    print()
    print("  move needed just to break even:")
    for bars, label in ((1, "scalp, same bar"), (4, "1h hold"),
                        (16, "4h hold"), (96, "1d hold")):
        print(f"    {label:20s} > {ROUND_TRIP:.2f}%")
        break
    print(f"""
  A {ROUND_TRIP:.2f}% round trip means intraday needs a >{ROUND_TRIP:.2f}%
  move per trade, net, after the move has already happened. On 15m bars the
  median absolute bar move is what decides whether that is plausible.
""")
    return ROUND_TRIP


def bar_moves():
    print("=" * 72)
    print("  HOW BIG ARE 15m MOVES?")
    print("=" * 72)
    try:
        from engine import load
    except Exception as e:
        print("  engine import failed:", e)
        return
    for sym in ("BTCUSD", "ETHUSD"):
        df = load(sym, "15m", source="delta")
        if len(df) < 500:
            print(f"  {sym}: only {len(df)} bars, skipping")
            continue
        r = (df["close"] / df["close"].shift(1) - 1) * 100
        print(f"\n  --- {sym}  ({len(df):,} bars, "
              f"{str(df.index[0])[:10]} to {str(df.index[-1])[:10]}) ---")
        for k in (1, 4, 16, 96):
            agg = df["close"].pct_change(k).abs() * 100
            print(f"    {k:>3d} bars ({k*15//60:>2d}h): median |move| "
                  f"{agg.median():5.3f}%   p90 {agg.quantile(.9):5.3f}%   "
                  f"frac > {ROUND_TRIP:.2f}%: {(agg > ROUND_TRIP).mean()*100:4.1f}%")


def main():
    fees()
    bar_moves()
    print("=" * 72)
    print("""
WHAT THIS DOES AND DOES NOT TELL YOU

It tells you the size of the fee hurdle and whether intraday bar movement is
large enough to clear it. It does NOT tell you whether a strategy can capture
that movement -- that needs an actual backtest, which is sweep_intraday.py.

The number to keep in mind for that backtest: the current winner, order block
plus sentiment gate on ETHUSD 1d, needed 129 trades over six years to reach
Sharpe 0.94. Intraday generates far more trades, which sounds like an
advantage, but it also means far more fees against the same underlying edge.
""")


if __name__ == "__main__":
    main()
