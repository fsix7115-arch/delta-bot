"""Run the sentiment-gated hybrid on 6 years of Binance data.

This is THE open question. On 2 years of Delta data `ob_sent_gate_25_75` on
ETHUSD 1d printed Sharpe 2.88, P(loss) 1.3% and a positive p5 -- far better
than anything else in the project. The plain order block did the same thing
(1.01 on 2y) and then fell to 0.60 on 6y once the 2020 crash and 2022 bear
market were included. So the 2.88 is assumed to be a selection artefact until
this script says otherwise.

Uses real funding rates and runs a 2x/3x cost stress. Sentiment is read
point-in-time via strategies_v2._sentiment_at, so no bar can see a Fear &
Greed reading published after it.
"""
import os
import sys

import numpy as np
import pandas as pd

import strategies_smc as M
import strategies_v2 as V2
from engine import load, run, metrics

HERE = os.path.dirname(os.path.abspath(__file__))
SENT = os.path.join(HERE, "data", "sentiment", "fear_greed.csv")
IS_FRAC = 0.55
OUT = os.path.join(HERE, "results", "hybrid_6y.csv")


def build(df, sent, lo, hi):
    """Order block entries suppressed when 5-day mean F&G is extreme."""
    a = M.order_block_trade(df, impulse_atr=1.0, max_age=30, hold_bars=8)
    fng = V2._sentiment_at(sent, df.index)
    avg = fng.rolling(5, min_periods=1).mean().shift(1)
    return pd.Series(np.where((avg < lo) | (avg > hi), 0.0, a), index=df.index)


def build_sent_trend(df, sent, lo, hi):
    """Sentiment-gated trend as a reference point.

    s_sentiment_trend is a FACTORY: it returns f(df, sent), and it already
    applies its own F&G gate from fng_floor/fng_cap. So no second gate here --
    doing both would stack two identical filters and change the meaning of the
    comparison.
    """
    return V2.s_sentiment_trend(50, 200, 14, lo, hi)(df, sent)


CASES = []
for lo, hi in ((25, 75), (0, 101), (20, 80), (30, 70)):
    for sym, res in (("ETHUSD", "1d"), ("ETHUSD", "4h"), ("BTCUSD", "1d")):
        CASES.append((f"ob_gate_{lo}_{hi}", sym, res, lo, hi))
for sym, res in (("ETHUSD", "1d"), ("ETHUSD", "4h")):
    CASES.append(("sent_trend_plain", sym, res, 0, 101))


def main():
    src = os.environ.get("SOURCE", "binance")
    sent = V2.load_sentiment(SENT)
    rows = []
    for name, sym, res, lo, hi in CASES:
        df = load(sym, res, source=src)
        if len(df) < 200:
            print(f"skip {name} {sym} {res}: only {len(df)} bars")
            continue
        oos = df.iloc[int(len(df) * IS_FRAC):]
        fn = build if name.startswith("ob") else build_sent_trend
        # asfloat: some generators return a non-numeric series (e.g. object dtype
        # from a bare df column), which makes engine.run's isnan check blow up.
        sig = pd.Series(np.asarray(fn(oos, sent, lo, hi), dtype=float),
                        index=oos.index)
        eq, tr = run(oos, sig, stop=0.035, risk=0.5)
        m = metrics(eq, tr, res)
        bh = oos["close"].iloc[-1] / oos["close"].iloc[0] - 1
        m2 = metrics(*run(oos, sig, stop=0.035, risk=0.5,
                          fee=0.001, slip=0.0008), res)
        rows.append({
            "name": name, "symbol": sym, "res": res, "gate": f"{lo}-{hi}",
            "bars": len(oos), "in_market_pct": round(float((sig != 0).mean()) * 100, 1),
            "sharpe": m["sharpe"], "sharpe_2x": m2["sharpe"],
            "cagr": m["cagr"], "max_dd": m["max_dd"],
            "trades": m["n_trades"], "win": m["win_rate"], "pf": m["profit_factor"],
            "avg_bars": m["avg_bars"], "degenerate": m["degenerate"],
            "buy_hold": bh, "alpha": m["total_return"] - bh,
        })
        r = rows[-1]
        print(f"{name:18s} {sym} {res:3s} gate={lo}-{hi:<4} "
              f"sh={r['sharpe']:6.2f} 2x={r['sharpe_2x']:6.2f} "
              f"trades={r['trades']:4d} dd={r['max_dd']*100:6.1f}% "
              f"bh={r['buy_hold']*100:+6.1f}%", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}")
    print("\n=== ranked by Sharpe (need >=30 trades, not degenerate) ===")
    ok = out[(out["trades"] >= 30) & (~out["degenerate"])]
    for _, r in ok.sort_values("sharpe", ascending=False).iterrows():
        print(f"  {r['name']:18s} {r['symbol']} {r['res']:3s} "
              f"sh={r['sharpe']:6.2f} trades={r['trades']:4d} "
              f"cagr={r['cagr']*100:+6.1f}% bh={r['buy_hold']*100:+6.1f}%")
    if ok.empty:
        print("  (none)")
    print("\nreference: plain order block on 6y = Sharpe 0.60 (ETH 1d, 78 trades)")
    print("if nothing here clears ~0.60, the 2.88 was a 2-year artefact")


if __name__ == "__main__":
    main()
