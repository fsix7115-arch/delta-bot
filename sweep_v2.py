"""Backtest the 2026 strategy round: SuperTrend, VWAP reversion, sentiment-gated.

Sentiment strategies read the 2018->now Fear & Greed series. Every sentiment
value is shifted so a bar can only use a reading published before it.
"""
import itertools
import os
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor

import strategies as S
import strategies_v2 as V2
from engine import load, run, metrics, load_funding

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
SENT = os.path.join(HERE, "data", "sentiment", "fear_greed.csv")
IS_FRAC = 0.55
SYMBOLS = ["BTCUSD", "ETHUSD"]
RESOLUTIONS = ["4h", "1d"]

STRATS = [
    ("supertrend_10_3", V2.s_supertrend(10, 3.0), False),
    ("supertrend_14_2.5", V2.s_supertrend(14, 2.5), False),
    ("supertrend_20_3", V2.s_supertrend(20, 3.0), False),
    ("vwap_48", V2.s_vwap_reversion(48, 1.8), False),
    ("vwap_96", V2.s_vwap_reversion(96, 1.8), False),
    ("sent_trend_20_50", V2.s_sentiment_trend(20, 50, fng_floor=25, fng_cap=75), True),
    ("sent_trend_20_50_wide", V2.s_sentiment_trend(20, 50, fng_floor=15, fng_cap=85), True),
    ("sent_trend_9_21", V2.s_sentiment_trend(9, 21, fng_floor=25, fng_cap=75), True),
    ("fng_div_c10", V2.s_fng_divergence(10, "contrarian"), True),
    ("fng_div_m10", V2.s_fng_divergence(10, "momentum"), True),
    ("fng_div_c20", V2.s_fng_divergence(20, "contrarian"), True),
    # existing leaders, kept in the table as the benchmark
    ("adx_trend_20_50", S.s_adx_trend(20, 50, 14, 20), False),
]
STOPS = [None, 0.02, 0.035]


def evaluate(task):
    sym, res, sidx, stop, source = task
    name, strat, needs_sent = STRATS[sidx]
    df = load(sym, res, source=source)
    funding = load_funding(sym) if source == "binance" else None
    split = int(len(df) * IS_FRAC)
    isdf, oosdf = df.iloc[:split], df.iloc[split:]
    sent = V2.load_sentiment(SENT) if needs_sent else None
    try:
        isig = strat(isdf, sent) if needs_sent else strat(isdf)
        osig = strat(oosdf, sent) if needs_sent else strat(oosdf)
    except Exception:
        return None
    iseq, itr = run(isdf, isig, stop=stop, risk=0.5, funding=funding)
    im = metrics(iseq, itr, res)
    if not itr or im["n_trades"] < 8:
        return None
    oeq, otr = run(oosdf, osig, stop=stop, risk=0.5, funding=funding)
    om = metrics(oeq, otr, res)
    seq, str_ = run(oosdf, osig, stop=stop, risk=0.5, fee=0.001, slip=0.0008,
                    funding=funding)
    sm = metrics(seq, str_, res)
    bh = oosdf["close"].iloc[-1] / oosdf["close"].iloc[0] - 1
    bpy = {"4h": 2190, "1d": 365}[res]
    bh_cagr = (1 + bh) ** (bpy / max(len(oosdf), 1)) - 1
    return {"strategy": name, "symbol": sym, "res": res, "stop": stop,
            "sentiment": needs_sent, "source": source,
            "is_sharpe": im["sharpe"], "oos_sharpe": om["sharpe"],
            "oos_cagr": om["cagr"], "oos_dd": om["max_dd"],
            "oos_trades": om["n_trades"], "oos_win": om["win_rate"],
            "oos_pf": om["profit_factor"], "stress_sharpe": sm["sharpe"],
            "bh_cagr": bh_cagr, "alpha": om["cagr"] - bh_cagr}


def main():
    source = os.environ.get("SOURCE", "delta")
    out = os.path.join(RES, "round2_delta.csv" if source == "delta" else "round2_6y.csv")
    tasks = list(itertools.product(SYMBOLS, RESOLUTIONS, range(len(STRATS)),
                                   STOPS, [source]))
    print(f"evaluating {len(tasks)} configs (source={source})", flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=max(2, os.cpu_count() - 1)) as ex:
        for r in ex.map(evaluate, tasks, chunksize=4):
            if r:
                rows.append(r)
    d = pd.DataFrame(rows)
    if d.empty:
        print("nothing valid")
        return
    d = d.sort_values("oos_sharpe", ascending=False)
    d.to_csv(out, index=False)
    print(f"\nwrote {out} ({len(d)} rows)\n")
    cols = ["strategy", "symbol", "res", "stop", "oos_sharpe", "oos_cagr",
            "oos_dd", "oos_trades", "oos_pf", "stress_sharpe", "bh_cagr", "alpha"]
    print("TOP 15")
    print(d.head(15)[cols].round(3).to_string(index=False))
    print("\n=== per-strategy best ===")
    for name, g in d.groupby("strategy"):
        b = g.loc[g.oos_sharpe.idxmax()]
        print(f"{name:22s} best {b.oos_sharpe:6.2f}  {b.symbol} {b.res} "
              f"stop={b.stop}  trades={int(b.oos_trades):4d}  alpha={b.alpha*100:+6.1f}%")
    ok = d[(d.oos_sharpe > 0.5) & (d.stress_sharpe > 0) & (d.oos_trades >= 20)]
    print(f"\npasses bar: {len(ok)} / {len(d)}")


if __name__ == "__main__":
    main()
