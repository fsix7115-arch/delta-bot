"""Backtest the mechanised SMC patterns from a prose playbook.

Reports each pattern's Sharpe, trade count and alpha vs buy & hold on Delta's
own 2-year data, at realistic costs. Anything that does not survive here is
documented as unsupported, not quietly kept.
"""
import itertools
import os
import pandas as pd
from concurrent.futures import ProcessPoolExecutor

import strategies_smc as M
from engine import load, run, metrics

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
IS_FRAC = 0.55
SYMBOLS = ["BTCUSD", "ETHUSD"]
RESOLUTIONS = ["4h", "1d"]


def evaluate(task):
    kind, sym, res, p1, p2, p3 = task
    df = load(sym, res, source="delta")
    oos = df.iloc[int(len(df) * IS_FRAC):]
    if kind == "fvg":
        sig = M.fvg_trade(oos, atr_mult=p1, max_age=p2)
        stop, tgt = p3, p3 * 3
    elif kind == "grab":
        sig = M.liquidity_grab(oos, lookback=p1)
        stop, tgt = p2, p2 * 2.5
    elif kind == "ob":
        sig = M.order_block_trade(oos, impulse_atr=p1, max_age=p2)
        stop, tgt = p3, p3 * 3
    else:
        sig = M.bos_choch_trade(oos, left=p1, right=p2)
        stop, tgt = p3, p3 * 3
    eq, tr = run(oos, sig, stop=stop, risk=0.5)
    m = metrics(eq, tr, res)
    if m["n_trades"] < 10:
        return None
    bh = oos["close"].iloc[-1] / oos["close"].iloc[0] - 1
    bpy = {"4h": 2190, "1d": 365}[res]
    bh_cagr = (1 + bh) ** (bpy / max(len(oos), 1)) - 1
    return {"kind": kind, "symbol": sym, "res": res, "p1": p1, "p2": p2, "p3": p3,
            "sharpe": m["sharpe"], "cagr": m["cagr"], "dd": m["max_dd"],
            "trades": m["n_trades"], "win": m["win_rate"], "pf": m["profit_factor"],
            "bh_cagr": bh_cagr, "alpha": m["cagr"] - bh_cagr}


def main():
    tasks = []
    for sym, res in itertools.product(SYMBOLS, RESOLUTIONS):
        for a in (0.3, 0.6, 1.0):                     # fvg atr_mult
            for age in (10, 20, 40):
                for sl in (0.02, 0.035):
                    tasks.append(("fvg", sym, res, a, age, sl))
        for lb in (10, 20, 50):                      # liquidity grab
            for sl in (0.02, 0.03):
                tasks.append(("grab", sym, res, lb, sl, 0.02))
        for ia in (1.0, 2.0, 3.0):                    # order block
            for age in (15, 30, 60):
                for sl in (0.02, 0.035):
                    tasks.append(("ob", sym, res, ia, age, sl))
        for lf in (2, 3, 5):                         # bos/choch
            for sl in (0.02, 0.035):
                tasks.append(("bos", sym, res, lf, lf, sl))
    print(f"evaluating {len(tasks)} configs", flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=max(2, os.cpu_count() - 1)) as ex:
        for r in ex.map(evaluate, tasks, chunksize=6):
            if r:
                rows.append(r)
    d = pd.DataFrame(rows)
    if d.empty:
        print("no pattern produced enough trades")
        return
    d = d.sort_values("sharpe", ascending=False)
    d.to_csv(os.path.join(RES, "smc.csv"), index=False)
    print(f"wrote results/smc.csv ({len(d)} valid)\n")
    print("TOP 10")
    print(d.head(10).to_string(index=False))
    print("\n=== per-pattern summary ===")
    for k, g in d.groupby("kind"):
        print(f"{k:5s} n={len(g):3d}  best={g.sharpe.max():6.2f}  "
              f"median={g.sharpe.median():6.2f}  "
              f"profitable={int((g.sharpe > 0).sum()):3d}/{len(g):3d}  "
              f"max_trades={int(g.trades.max())}")
    ok = d[(d.sharpe > 0.5) & (d.trades >= 20) & (d.alpha > 0)]
    print(f"\npasses Sharpe>0.5 AND >=20 trades AND positive alpha: {len(ok)}")
    if len(ok):
        print(ok.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
