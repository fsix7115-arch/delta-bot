"""Monte Carlo on the best round-2 candidates, head-to-head with order block."""
import os
import numpy as np
import pandas as pd

import strategies_smc as M
import strategies_v2 as V2
from engine import load, run, metrics
from monte_carlo import equity_from_pnls, sharpe_from_curve

HERE = os.path.dirname(os.path.abspath(__file__))
SENT = os.path.join(HERE, "data", "sentiment", "fear_greed.csv")
IS_FRAC = 0.55
RNG = 0.02

CASES = [
    ("order_block ETH 4h (incumbent)", "ETHUSD", "4h",
     lambda d, s: M.order_block_trade(d, impulse_atr=1.0, max_age=30, hold_bars=8)),
    ("fng_div_c20 ETH 4h", "ETHUSD", "4h",
     lambda d, s: V2.s_fng_divergence(20, "contrarian")(d, s)),
    ("sent_trend_wide ETH 1d", "ETHUSD", "1d",
     lambda d, s: V2.s_sentiment_trend(20, 50, fng_floor=15, fng_cap=85)(d, s)),
    ("sent_trend_20_50 ETH 4h", "ETHUSD", "4h",
     lambda d, s: V2.s_sentiment_trend(20, 50)(d, s)),
    ("fng_div_c10 BTC 4h", "BTCUSD", "4h",
     lambda d, s: V2.s_fng_divergence(10, "contrarian")(d, s)),
]


def main():
    sent = V2.load_sentiment(SENT)
    print(f"{'case':32s} {'trd':>4s} {'CAGR':>7s} {'Shrp':>6s} {'P(loss)':>8s} "
          f"{'p5':>7s} {'wrstDD':>7s}")
    rows = []
    for label, sym, res, fn in CASES:
        df = load(sym, res, source="delta")
        oos = df.iloc[int(len(df) * IS_FRAC):]
        sig = fn(oos, sent)
        eq, tr = run(oos, sig, stop=RNG, risk=0.5)
        m = metrics(eq, tr, res)
        if m["n_trades"] < 20:
            print(f"{label:32s} too few trades ({int(m['n_trades'])})")
            continue
        pnls = [t["pnl"] for t in tr]
        rng = np.random.default_rng(23)
        f, dds = [], []
        for _ in range(2000):
            c = equity_from_pnls(rng.choice(pnls, size=len(pnls), replace=True))
            f.append(c.iloc[-1] - 1)
            dds.append((c / c.cummax() - 1).min())
        f = np.array(f)
        rows.append({"case": label, "trades": m["n_trades"], "cagr": m["cagr"],
                     "sharpe": m["sharpe"], "win": m["win_rate"],
                     "pf": m["profit_factor"], "p_loss": float((f <= 0).mean()),
                     "p05": float(np.percentile(f, 5)),
                     "dd_worst": float(np.percentile(dds, 5))})
        print(f"{label:32s} {m['n_trades']:4.0f} {m['cagr']*100:6.1f}% "
              f"{m['sharpe']:6.2f} {(f<=0).mean()*100:7.1f}% "
              f"{np.percentile(f,5)*100:6.1f}% {np.percentile(dds,5)*100:6.1f}%")
    if rows:
        d = pd.DataFrame(rows).sort_values("p_loss")
        d.to_csv(os.path.join(HERE, "results", "round2_monte_carlo.csv"), index=False)
        print("\nwrote results/round2_monte_carlo.csv")
        print("\n=== ranking by P(loss), lower is better ===")
        for _, r in d.iterrows():
            print(f"  {r.case:32s} P(loss)={r.p_loss*100:5.1f}%  "
                  f"p5={r.p05*100:6.1f}%  Sharpe={r.sharpe:.2f}")


if __name__ == "__main__":
    main()
