"""Validate the order-block winner on 6 years of Binance data (2020 -> now).

Why this matters: the current result is 2 years of Delta data, and Delta only
serves 2 years, so the winner has never seen a bull market or the 2020 crash.
Binance is the only source that covers those regimes. If the edge is real it
should survive the crash and the bull; if it only works in a falling market it
will not.

Funding is modelled from real Binance funding rates (the engine charges longs
when the rate is positive), and OOS is re-run at 2x fees to test cost headroom.
"""
import itertools
import os
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor

import strategies_smc as M
import strategies_v2 as V2
from engine import load, run, metrics, load_funding

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
SENT = os.path.join(HERE, "data", "sentiment", "fear_greed.csv")
IS_FRAC = 0.55
SYMBOLS = ["BTCUSD", "ETHUSD"]
RESOLUTIONS = ["4h", "1d"]


def build_cases():
    """Order block across a compact param grid (2 CPU cores, 6y data is slow)."""
    cases = []
    for ia in (0.6, 1.0, 1.5):
        for age in (30,):
            for hb in (8,):
                cases.append((f"ob_ia{ia}_age{age}_h{hb}", ia, age, hb))
    return cases


CASES = build_cases()


def evaluate(task):
    sym, res, cidx, stop = task
    name, ia, age, hb = CASES[cidx]
    df = load(sym, res, source="binance")
    funding = load_funding(sym)
    split = int(len(df) * IS_FRAC)
    isdf, oosdf = df.iloc[:split], df.iloc[split:]
    isig = M.order_block_trade(isdf, impulse_atr=ia, max_age=age, hold_bars=hb)
    osig = M.order_block_trade(oosdf, impulse_atr=ia, max_age=age, hold_bars=hb)
    iseq, itr = run(isdf, isig, stop=stop, risk=0.5, funding=funding)
    im = metrics(iseq, itr, res)
    if not itr or im["n_trades"] < 20:
        return None
    oeq, otr = run(oosdf, osig, stop=stop, risk=0.5, funding=funding)
    om = metrics(oeq, otr, res)
    seq, str_ = run(oosdf, osig, stop=stop, risk=0.5, fee=0.001, slip=0.0008,
                    funding=funding)
    sm = metrics(seq, str_, res)
    nfeq, nftr = run(oosdf, osig, stop=stop, risk=0.5, funding=None)
    nfm = metrics(nfeq, nftr, res)
    bh = oosdf["close"].iloc[-1] / oosdf["close"].iloc[0] - 1
    bpy = {"4h": 2190, "1d": 365}[res]
    return {"case": name, "impulse_atr": ia, "max_age": age, "hold": hb,
            "symbol": sym, "res": res, "stop": stop,
            "is_sharpe": im["sharpe"], "is_trades": im["n_trades"],
            "oos_sharpe": om["sharpe"], "oos_cagr": om["cagr"],
            "oos_dd": om["max_dd"], "oos_trades": om["n_trades"],
            "oos_win": om["win_rate"], "oos_pf": om["profit_factor"],
            "stress_sharpe": sm["sharpe"],
            "funding_drag": nfm["cagr"] - om["cagr"],
            "bh_cagr": (1 + bh) ** (bpy / max(len(oosdf), 1)) - 1}


def main():
    tasks = list(itertools.product(SYMBOLS, RESOLUTIONS, range(len(CASES)),
                                   [None, 0.02, 0.035]))
    print(f"6y Binance: evaluating {len(tasks)} configs", flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=max(2, os.cpu_count() - 1)) as ex:
        for r in ex.map(evaluate, tasks, chunksize=4):
            if r:
                rows.append(r)
    d = pd.DataFrame(rows)
    if d.empty:
        print("nothing valid")
        return
    d["alpha"] = d.oos_cagr - d.bh_cagr
    d = d.sort_values("oos_sharpe", ascending=False)
    out = os.path.join(RES, "orderblock_6y.csv")
    d.to_csv(out, index=False)
    print(f"\nwrote {out} ({len(d)} rows)\n")
    cols = ["case", "symbol", "res", "stop", "oos_sharpe", "oos_cagr", "oos_dd",
            "oos_trades", "oos_pf", "stress_sharpe", "funding_drag", "bh_cagr", "alpha"]
    print("TOP 15")
    print(d.head(15)[cols].round(3).to_string(index=False))
    print("\n=== buy & hold, same 6y window ===")
    for sym in SYMBOLS:
        for res in RESOLUTIONS:
            dfx = load(sym, res, source="binance")
            oos = dfx.iloc[int(len(dfx) * IS_FRAC):]
            b = oos["close"].iloc[-1] / oos["close"].iloc[0] - 1
            bpy = {"4h": 2190, "1d": 365}[res]
            c = (1 + b) ** (bpy / max(len(oos), 1)) - 1
            print(f"  BH {sym} {res}: total {b*100:7.1f}%  cagr {c*100:6.1f}%")
    ok = d[(d.oos_sharpe > 0.5) & (d.stress_sharpe > 0) & (d.oos_trades >= 40)]
    print(f"\npasses bar: {len(ok)} / {len(d)}")


if __name__ == "__main__":
    main()
