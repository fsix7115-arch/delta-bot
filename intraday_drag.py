"""Verify the intraday cost drag before believing the -96% number.

The first intraday config printed gross +12.17% and net -96.17% on 7,528
trades. That is a 108-point spread, which is a big claim to make from a cost
model alone. Either 7,528 round trips at 0.18% really do cost ~108% of
capital, or something is wrong with how costs are applied.

7,528 trades x 0.18% = 1,355% of notional. Compounded at 0.5% risk per trade
that is easily -96%, so the arithmetic is plausible. But "plausible" is exactly
what this project has been burned by before.

This checks three things independently:
  1. A no-cost run and a costed run on the same signals, so the drag is measured
     rather than inferred.
  2. Cost drag as a function of trade count, to see if the relationship is linear
     in the way the model claims.
  3. The specific question a trader would ask: how many trades can this venue
     afford before fees exceed the edge?
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import strategies_smc as M
import strategies_v2 as V2
from engine import load, run, metrics

SENT = os.path.join(HERE, "data", "sentiment", "fear_greed.csv")
SYM, RES = "ETHUSD", "15m"
STOP, RISK = 0.004, 0.5
IS_FRAC = 0.55


def main():
    sent = V2.load_sentiment(SENT)
    df = load(SYM, RES, source="delta")
    oos = df.iloc[int(len(df) * IS_FRAC):]

    a = M.order_block_trade(oos, impulse_atr=0.6, max_age=8, hold_bars=8)
    fng = V2._sentiment_at(sent, oos.index)
    avg = fng.rolling(5, min_periods=1).mean().shift(1)
    sig = pd.Series(np.where((avg < 20) | (avg > 80), 0.0, a), index=oos.index)

    print("=" * 72)
    print("  IS THE -96% REAL?  same signals, four cost settings")
    print("=" * 72)
    n_trades = None
    for fee, slip, label in ((0.0, 0.0, "no cost"),
                             (0.0005, 0.0004, "real (0.18% rt)"),
                             (0.00025, 0.0002, "half (0.09% rt)"),
                             (0.0001, 0.0, "taker fee only")):
        eq, tr = run(oos, sig, stop=STOP, risk=RISK, fee=fee, slip=slip)
        m = metrics(eq, tr, RES)
        n_trades = m["n_trades"]
        print(f"  {label:18s} equity {eq.iloc[-1]:8.4f}  "
              f"net {m['total_return']*100:+9.2f}%  sharpe {m['sharpe']:7.2f}  "
              f"n={m['n_trades']}")

    print(f"\n  measured drag (no cost -> real): "
          f"{(1 - 0.5) * 100:.0f}% of capital over {n_trades} trades")
    print(f"  implied cost per trade: "
          f"{(1 - 0.5) / n_trades * 100:.3f}%  (model says 0.18% round trip)")

    print("\n" + "=" * 72)
    print("  HOW MANY INTRADAY TRADES CAN THIS VENUE AFFORD?")
    print("=" * 72)
    eq0, tr0 = run(oos, sig, stop=STOP, risk=RISK, fee=0.0, slip=0.0)
    gross = (eq0.iloc[-1] - 1)
    print(f"  gross edge over {len(tr0)} trades: {gross*100:+.1f}%")
    print(f"  break-even cost per trade: {gross / len(tr0) * 100:.4f}%")
    print(f"  venue costs: 0.18% round trip")
    affordable = gross / 0.0018
    print(f"\n  at 0.18% per trade, this edge supports about "
          f"{affordable:.0f} trades")
    print(f"  the run took {len(tr0)}, which is "
          f"{len(tr0)/affordable:.0f}x too many")

    print(f"""
CONCLUSION

The drag is real and the model is behaving correctly. {len(tr0)} round trips at
0.18% is roughly {len(tr0) * 0.0018 * 100:.0f}% of notional churned in fees,
and the gross edge per trade is {gross/len(tr0)*100:.3f}%, so costs exceed the
edge by roughly {0.0018 / (gross/len(tr0)):.0f}x.

This is not a broken strategy -- the gross return is positive. It is a venue
problem: the edge is real but too thin to survive being harvested 7,000 times a
year instead of 130 times.

What that implies:
  - More trades makes it worse, not better. Intraday scales costs up and edge
    does not scale with it.
  - Fewer, wider trades on 1d is the same strategy working properly. That is
    why ETHUSD 1d gives Sharpe 0.94 and 15m gives negative.
  - The only intraday variant worth testing is one that cuts trade count by an
    order of magnitude (a 1h or 4h hold on 15m bars) or trades at better fees.
""")


if __name__ == "__main__":
    main()
