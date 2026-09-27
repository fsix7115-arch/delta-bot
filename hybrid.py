"""Hybrid: order block entry gated by sentiment, and order block with a
sentiment-confirmed trend filter.

Motivation: the two round-2 leaders failed in different ways.
  - order block ETH 4h  : best return (21% CAGR) but P(loss) 11.3%, p5 -12.8%
  - F&G divergence ETH 4h: lower return (12% CAGR) but a much softer p5 -8.4%
If their failure modes are independent, requiring BOTH to agree should cut the
left tail without giving up most of the return. If they are correlated, the
hybrid will just be a noisier version of one of them -- which is itself worth
knowing.

All sentiment reads are shifted so no bar sees a reading published after it.
"""
import os
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor

import strategies_smc as M
import strategies_v2 as V2
from engine import load, run, metrics
from monte_carlo import equity_from_pnls

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
SENT = os.path.join(HERE, "data", "sentiment", "fear_greed.csv")
IS_FRAC = 0.55
SYMBOLS = ["BTCUSD", "ETHUSD"]
RESOLUTIONS = ["4h", "1d"]


def ob(sym_df, ia=1.0, age=30, hb=8):
    return M.order_block_trade(sym_df, impulse_atr=ia, max_age=age, hold_bars=hb)


def hybrid_and(df, sent, ia=1.0, age=30, hb=8, lookback=20):
    """Trade only where an order block entry AND a sentiment divergence agree."""
    a = ob(df, ia, age, hb)
    b = V2.s_fng_divergence(lookback, "contrarian")(df, sent)
    return pd.Series(np.where((a != 0) & (a == b), a, 0.0), index=df.index)


def hybrid_or(df, sent, ia=1.0, age=30, hb=8, lookback=20):
    """Trade on either, but require the sentiment side to not actively disagree."""
    a = ob(df, ia, age, hb)
    b = V2.s_fng_divergence(lookback, "contrarian")(df, sent)
    agree = np.where((a != 0) & (b != 0) & (a != b), 0.0, 1.0)
    return pd.Series(np.where(a != 0, a, np.where(b != 0, b * agree, 0.0)),
                     index=df.index)


def ob_sent_gate(df, sent, ia=1.0, age=30, hb=8, floor=15, cap=85):
    """Order block entries, but flat while sentiment is at an extreme."""
    a = ob(df, ia, age, hb)
    fng = V2._sentiment_at(sent, df.index)
    if fng is None:
        return a
    avg = fng.rolling(5, min_periods=1).mean().shift(1)
    return pd.Series(np.where((avg < floor) | (avg > cap), 0.0, a), index=df.index)


VARIANTS = [
    ("ob_only", lambda d, s: ob(d)),
    ("hybrid_and_c20", lambda d, s: hybrid_and(d, s, lookback=20)),
    ("hybrid_or_c20", lambda d, s: hybrid_or(d, s, lookback=20)),
    ("hybrid_and_c10", lambda d, s: hybrid_and(d, s, lookback=10)),
    ("ob_gate_15_85", lambda d, s: ob_sent_gate(d, s, floor=15, cap=85)),
    ("ob_gate_25_75", lambda d, s: ob_sent_gate(d, s, floor=25, cap=75)),
]
STOPS = [0.02, 0.035]


def evaluate(task):
    name, sym, res, stop = task
    fn = dict(VARIANTS)[name]
    df = load(sym, res, source="delta")
    sent = V2.load_sentiment(SENT)
    oos = df.iloc[int(len(df) * IS_FRAC):]
    try:
        sig = fn(oos, sent)
    except Exception:
        return None
    eq, tr = run(oos, sig, stop=stop, risk=0.5)
    m = metrics(eq, tr, res)
    if m["n_trades"] < 20:
        return None
    pnls = [t["pnl"] for t in tr]
    rng = np.random.default_rng(31)
    f = []
    for _ in range(1500):
        c = equity_from_pnls(rng.choice(pnls, size=len(pnls), replace=True))
        f.append(c.iloc[-1] - 1)
    f = np.array(f)
    seq, str_ = run(oos, sig, stop=stop, risk=0.5, fee=0.001, slip=0.0008)
    sm = metrics(seq, str_, res)
    bh = oos["close"].iloc[-1] / oos["close"].iloc[0] - 1
    bpy = {"4h": 2190, "1d": 365}[res]
    return {"variant": name, "symbol": sym, "res": res, "stop": stop,
            "sharpe": m["sharpe"], "cagr": m["cagr"], "dd": m["max_dd"],
            "trades": m["n_trades"], "win": m["win_rate"], "pf": m["profit_factor"],
            "p_loss": float((f <= 0).mean()), "p05": float(np.percentile(f, 5)),
            "stress_sharpe": sm["sharpe"],
            "alpha": m["cagr"] - (1 + bh) ** (bpy / max(len(oos), 1)) - 1}


def main():
    tasks = [(n, s, r, st) for n, _ in VARIANTS
             for s, r in [(a, b) for a in SYMBOLS for b in RESOLUTIONS]
             for st in STOPS]
    print(f"evaluating {len(tasks)} hybrid configs", flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=max(2, os.cpu_count() - 1)) as ex:
        for r in ex.map(evaluate, tasks, chunksize=2):
            if r:
                rows.append(r)
    d = pd.DataFrame(rows)
    if d.empty:
        print("nothing valid")
        return
    d = d.sort_values("p_loss")
    d.to_csv(os.path.join(RES, "hybrid.csv"), index=False)
    print(f"\nwrote results/hybrid.csv ({len(d)} rows)\n")
    cols = ["variant", "symbol", "res", "stop", "sharpe", "cagr", "dd", "trades",
            "win", "pf", "p_loss", "p05", "stress_sharpe", "alpha"]
    print(d[cols].round(3).to_string(index=False))
    print("\n=== ranked by P(loss) ===")
    for _, r in d.iterrows():
        print(f"  {r.variant:16s} {r.symbol:7s} {r.res:3s} stop={str(r.stop):5s} "
              f"P(loss)={r.p_loss*100:5.1f}%  p5={r.p05*100:6.1f}%  "
              f"Sharpe={r.sharpe:5.2f}  trades={int(r.trades):4d}")


if __name__ == "__main__":
    main()
