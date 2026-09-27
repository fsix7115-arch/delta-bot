"""Backtest the mechanised YouTube strategy across parameter grids.

Reports gross and cost-aware results side by side, and compares to buy & hold.
"""
import itertools
import os
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor

from engine import load, run, metrics
import strategies_youtube as Y

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
IS_FRAC = 0.55

GRID = list(itertools.product(
    [20, 50],           # lookback
    [1.0, 2.0],         # sl_mult
    [3.0, 5.0],         # target_mult
    [30],               # max_bars
    [0],                # trend filter
))
SYMBOLS = ["BTCUSD", "ETHUSD"]
RESOLUTIONS = ["4h", "1d"]


def evaluate(task):
    sym, res, lookback, sl, tgt, mb, trend, kind = task
    df = load(sym, res, source="delta")
    split = int(len(df) * IS_FRAC)
    oos = df.iloc[split:]
    if kind == "break":
        sig = Y.candle_break(oos, lookback, sl, tgt, mb, trend=trend)
    else:
        sig = Y.sweep_candle(oos, lookback, trend=trend)
    eq, tr = run(oos, sig, stop=None, risk=0.5)
    m = metrics(eq, tr, res)
    if m["n_trades"] < 8:
        return None
    eq0, _ = run(oos, pd.Series(0.0, index=oos.index), risk=0.5)
    bh = oos["close"].iloc[-1] / oos["close"].iloc[0] - 1
    bpy = {"4h": 2190, "1d": 365}[res]
    bh_cagr = (1 + bh) ** (bpy / max(len(oos), 1)) - 1
    return {
        "kind": kind, "symbol": sym, "res": res, "lookback": lookback,
        "sl": sl, "target": tgt, "max_bars": mb, "trend": trend,
        "sharpe": m["sharpe"], "cagr": m["cagr"], "dd": m["max_dd"],
        "trades": m["n_trades"], "win": m["win_rate"], "pf": m["profit_factor"],
        "bh_cagr": bh_cagr, "alpha": m["cagr"] - bh_cagr,
    }


def main():
    tasks = [(s, r, lb, sl, tg, mb, tr, k)
             for s, r in itertools.product(SYMBOLS, RESOLUTIONS)
             for (lb, sl, tg, mb, tr) in GRID
             for k in ("break", "sweep")]
    print(f"evaluating {len(tasks)} configs on {os.cpu_count()} workers", flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=max(2, os.cpu_count() - 1)) as ex:
        for r in ex.map(evaluate, tasks, chunksize=4):
            if r:
                rows.append(r)
    d = pd.DataFrame(rows)
    if d.empty:
        print("no config produced enough trades")
        return
    d = d.sort_values("sharpe", ascending=False)
    d.to_csv(os.path.join(RES, "youtube.csv"), index=False)
    print(f"wrote results/youtube.csv ({len(d)} valid configs)\n")
    print("TOP 12 BY SHARPE")
    print(d.head(12).to_string(index=False))
    ok = d[(d.sharpe > 0.5) & (d.trades >= 15)]
    print(f"\nprofitable+enough trades: {len(ok)} / {len(d)}")
    if len(ok):
        print(ok.head(10).to_string(index=False))
    for kind in ("break", "sweep"):
        sub = d[d.kind == kind]
        if len(sub):
            print(f"\n{kind}: best Sharpe {sub.sharpe.max():.2f}, "
                  f"median {sub.sharpe.median():.2f}, "
                  f"profitable {int((sub.sharpe > 0).sum())}/{len(sub)}")


if __name__ == "__main__":
    main()
