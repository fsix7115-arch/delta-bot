"""Vet the headline hybrid result before believing it.

`ob_gate_25_75` on ETHUSD 1d reported Sharpe 2.88, P(loss) 1.3% and a POSITIVE
p5 of +15.2% over 41 trades. That is far better than anything else found in
this project, which makes it the most likely candidate for an artefact.

Checks run here:
  1. Does the signal hold the position, or is it churning?
  2. Do fees actually get charged on both legs?
  3. Is the sentiment gate accidentally looking at the FUTURE?
  4. How much of the result survives doubling costs, and what does the
     buy-and-hold comparison look like on the same bars?
  5. How many configs were searched to find this one? (selection bias)
"""
import os
import numpy as np
import pandas as pd

import strategies_smc as M
import strategies_v2 as V2
from engine import load, run, metrics

HERE = os.path.dirname(os.path.abspath(__file__))
SENT = os.path.join(HERE, "data", "sentiment", "fear_greed.csv")
IS_FRAC = 0.55
SYMBOL, RES = "ETHUSD", "1d"
STOP = 0.035


def build(df, sent):
    a = M.order_block_trade(df, impulse_atr=1.0, max_age=30, hold_bars=8)
    fng = V2._sentiment_at(sent, df.index)
    avg = fng.rolling(5, min_periods=1).mean().shift(1)
    return pd.Series(np.where((avg < 25) | (avg > 75), 0.0, a), index=df.index)


def main():
    df = load(SYMBOL, RES, source="delta")
    sent = V2.load_sentiment(SENT)
    oos = df.iloc[int(len(df) * IS_FRAC):]
    sig = build(oos, sent)

    print(f"bars={len(oos)}  signal counts={sig.value_counts().to_dict()}")
    print(f"bars in market: {int((sig!=0).sum())}/{len(sig)} "
          f"({(sig!=0).sum()/len(sig)*100:.0f}%)\n")

    # 1) holding behaviour
    eq, tr = run(oos, sig, stop=STOP, risk=0.5)
    m = metrics(eq, tr, RES)
    print("1) HOLDING")
    print(f"   trades={int(m['n_trades'])}  avg_bars={m['avg_bars']:.1f}  "
          f"degenerate={m['degenerate']}")
    from collections import Counter
    print(f"   holding lengths: {Counter(t['bars'] for t in tr).most_common(5)}")
    print(f"   exit reasons  : {Counter(t['reason'] for t in tr).most_common()}\n")

    # 2) cost sanity: the same signals with zero costs must beat the real run
    e0, _ = run(oos, sig, stop=STOP, risk=0.5, fee=0.0, slip=0.0)
    e1, _ = run(oos, sig, stop=STOP, risk=0.5, fee=0.0005, slip=0.0004)
    print("2) COST WIRING")
    print(f"   zero-cost equity {e0.iloc[-1]:.3f}  real-cost equity {e1.iloc[-1]:.3f}")
    print(f"   cost drag {100*(e0.iloc[-1]-e1.iloc[-1])/e0.iloc[-1]:.2f}%  "
          f"(must be clearly positive)")
    if e1.iloc[-1] >= e0.iloc[-1]:
        print("   !! COSTS NOT BEING CHARGED — result is invalid")
    print()

    # 3) sentiment lookahead
    print("3) SENTIMENT LEAK CHECK")
    shifted = V2._sentiment_at(sent, oos.index)
    raw = sent.reindex(sent.index.union(oos.index)).ffill()
    raw = raw.reindex(oos.index, method="ffill")
    # compare the value the gate used with a version that is 10 days staler
    stale = V2._sentiment_at(sent, oos.index, lookback_days=10)
    n_diff = int((shifted.fillna(0) != stale.fillna(0)).sum())
    print(f"   bars where 1d-shift vs 10d-shift differ: {n_diff}/{len(oos)}")
    es, _ = run(oos, build(oos, stale), stop=STOP, risk=0.5)
    print(f"   equity with stale sentiment: {es.iloc[-1]:.3f} vs {e1.iloc[-1]:.3f}")
    if abs(es.iloc[-1] - e1.iloc[-1]) < 1e-9:
        print("   !! sentiment gate has NO effect on results")
    print()

    # 4) headline numbers + comparison
    print("4) HEADLINE")
    print(f"   Sharpe {m['sharpe']:.2f}  CAGR {m['cagr']*100:.1f}%  "
          f"DD {m['max_dd']*100:.1f}%  win {m['win_rate']*100:.0f}%  "
          f"PF {m['profit_factor']:.2f}")
    for fee, slp, lbl in ((0.001, 0.0008, "2x costs"), (0.0015, 0.0012, "3x costs")):
        e, t = run(oos, sig, stop=STOP, risk=0.5, fee=fee, slip=slp)
        mm = metrics(e, t, RES)
        print(f"   {lbl:9s}: equity {e.iloc[-1]:.3f}  Sharpe {mm['sharpe']:.2f}")
    bh = oos["close"].iloc[-1] / oos["close"].iloc[0] - 1
    print(f"   buy & hold same bars: {bh*100:+.1f}%  "
          f"(spread to strategy {100*(m['total_return']-bh):+.1f}pp)")
    print()

    # 5) selection bias
    n_cfg = 6 * 2 * 2 * 2   # variants x symbols x resolutions x stops
    print("5) SELECTION BIAS")
    print(f"   configs searched in hybrid.py: {n_cfg}")
    print(f"   winner trades: {int(m['n_trades'])} on {len(oos)} bars")
    print(f"   -> a +{m['cagr']*100:.0f}% CAGR pick is the MAX of "
          f"{n_cfg} correlated trials; expect a large optimistic bias.")


if __name__ == "__main__":
    main()
