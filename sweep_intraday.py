"""Intraday backtest: does the order-block edge survive 15m fees?

intraday_fees.py showed 15m bar movement is large enough to clear the 0.18%
round trip on roughly 29% (BTC) to 43% (ETH) of bars. That is necessary, not
sufficient: the question is whether the strategy's edge is big enough, and the
only way to know is to trade it.

Design constraints, all forced by 2 CPU cores and 96k bars per symbol:
  - Small grid. A full sweep of this size times out; the earlier 1h sweeps
    died at 2400s. Four impulse multipliers, two holds, one stop, two symbols.
  - Walk-forward split 55/45, same convention as every other sweep here, so
    numbers are comparable to the published results.
  - 2x cost stress on every config, because intraday is where cost assumptions
    do the most damage.

Reported per config: Sharpe, trades, win rate, profit factor, and the gross
return before fees. The gross column is diagnostic -- if gross is healthy and
net is not, the strategy logic is fine and only the venue is hostile, which is
a very different problem from a broken strategy.
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

IS_FRAC = 0.55
SENT = os.path.join(HERE, "data", "sentiment", "fear_greed.csv")
OUT = os.path.join(HERE, "results", "intraday.csv")

# Intraday stops must be tighter in absolute terms than a 1d stop, or a single
# 15m bar blows through them and the stop stops meaning anything.
STOPS = (0.004, 0.008)


def build(df, sent, ia, hold, gate=True):
    sig = M.order_block_trade(df, impulse_atr=ia, max_age=8, hold_bars=hold)
    if not gate or sent is None:
        return sig
    fng = V2._sentiment_at(sent, df.index)
    avg = fng.rolling(5, min_periods=1).mean().shift(1)
    return pd.Series(np.where((avg < 20) | (avg > 80), 0.0, sig), index=df.index)


def main():
    src = os.environ.get("SOURCE", "delta")
    sent = V2.load_sentiment(SENT) if os.path.exists(SENT) else None
    rows = []

    for sym in ("ETHUSD", "BTCUSD"):
        df = load(sym, "15m", source=src)
        if len(df) < 5000:
            print(f"skip {sym}: {len(df)} bars")
            continue
        oos = df.iloc[int(len(df) * IS_FRAC):]
        print(f"\n=== {sym} 15m  |  {len(df):,} bars total, "
              f"{len(oos):,} out-of-sample  ===", flush=True)
        print(f"{'imp':>4s} {'hold':>4s} {'stop':>6s} {'gate':>4s} "
              f"{'sharpe':>7s} {'2x':>6s} {'gross':>8s} {'net':>7s} "
              f"{'trades':>7s} {'win':>5s} {'pf':>5s} {'dd':>7s}", flush=True)

        for ia in (0.6, 1.0):
            for hold in (8, 24):
                for stop in STOPS:
                    for gate in (True, False):
                        sig = build(oos, sent, ia, hold, gate)
                        eq, tr = run(oos, sig, stop=stop, risk=0.5)
                        m = metrics(eq, tr, "15m")
                        m2 = metrics(*run(oos, sig, stop=stop, risk=0.5,
                                          fee=0.001, slip=0.0008), "15m")
                        # gross = what the same trades would have made with no
                        # costs at all, i.e. the pure price move captured
                        eq0, _ = run(oos, sig, stop=stop, risk=0.5,
                                     fee=0.0, slip=0.0)
                        gross = (eq0.iloc[-1] - 1) * 100
                        r = {
                            "symbol": sym, "impulse": ia, "hold": hold,
                            "stop": stop, "gate": gate,
                            "sharpe": m["sharpe"], "sharpe_2x": m2["sharpe"],
                            "gross_pct": gross, "net_pct": m["total_return"] * 100,
                            "trades": m["n_trades"], "win": m["win_rate"] * 100,
                            "pf": m["profit_factor"], "max_dd": m["max_dd"] * 100,
                            "degenerate": m["degenerate"],
                            "in_market_pct": float((sig != 0).mean()) * 100,
                        }
                        rows.append(r)
                        print(f"{ia:>4.1f} {hold:>4d} {stop*100:>5.2f}% "
                              f"{'yes' if gate else 'no':>4s} "
                              f"{m['sharpe']:>7.2f} {m2['sharpe']:>6.2f} "
                              f"{gross:>+7.2f}% {m['total_return']*100:>+6.2f}% "
                              f"{m['n_trades']:>7d} {m['win_rate']*100:>4.0f}% "
                              f"{m['profit_factor']:>5.2f} "
                              f"{m['max_dd']*100:>6.1f}%", flush=True)

    if not rows:
        print("no intraday data available")
        return
    d = pd.DataFrame(rows)
    d.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}")

    print("\n=== ranked by Sharpe (>=200 trades, not degenerate) ===")
    ok = d[(d["trades"] >= 200) & (~d["degenerate"])]
    if ok.empty:
        print("  (nothing cleared the trade-count floor)")
        print(f"  best raw sharpe: {d['sharpe'].max():.2f} "
              f"on {int(d.loc[d['sharpe'].idxmax(), 'trades'])} trades")
    for _, r in ok.sort_values("sharpe", ascending=False).head(8).iterrows():
        print(f"  {r['symbol']} ia={r['impulse']} hold={r['hold']} "
              f"stop={r['stop']*100:.1f}% gate={r['gate']}  "
              f"sh={r['sharpe']:.2f} 2x={r['sharpe_2x']:.2f} "
              f"gross={r['gross_pct']:+.1f}% net={r['net_pct']:+.1f}% "
              f"n={int(r['trades'])}")

    print(f"""
COMPARISON
  order block + sentiment, ETHUSD 1d, 6 years : Sharpe 0.94, net +18.5%
  these intraday runs                        : see table above

Read gross vs net. If gross is large and net is near zero, the pattern is
real and the venue is the problem, which points at wider holds, tighter
execution, or a limit-order strategy. If gross is also small, the edge does
not exist at this timeframe and no fee arrangement will create it.
""")


if __name__ == "__main__":
    main()
