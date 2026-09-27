"""Monte Carlo on the SMC order-block strategy after the lookahead fix."""
import os
import numpy as np
import pandas as pd

import strategies_smc as M
from engine import load, run, metrics
from monte_carlo import equity_from_pnls, sharpe_from_curve

HERE = os.path.dirname(os.path.abspath(__file__))
IS_FRAC = 0.55

CASES = [
    ("ETHUSD", "4h", dict(impulse_atr=1.0, max_age=30, hold_bars=8), 0.02),
    ("ETHUSD", "4h", dict(impulse_atr=1.0, max_age=15, hold_bars=8), 0.02),
    ("BTCUSD", "1d", dict(impulse_atr=1.0, max_age=30, hold_bars=8), 0.02),
    ("ETHUSD", "1d", dict(impulse_atr=1.0, max_age=30, hold_bars=8), 0.02),
]


def main():
    rows = []
    print(f"{'sym':7s} {'res':3s} {'trades':>6s} {'CAGR':>7s} {'Sharpe':>7s} "
          f"{'MC_med':>7s} {'p5':>7s} {'P(loss)':>8s} {'worstDD':>8s}")
    for sym, res, kw, stop in CASES:
        df = load(sym, res, source="delta")
        oos = df.iloc[int(len(df) * IS_FRAC):]
        sig = M.order_block_trade(oos, **kw)
        eq, tr = run(oos, sig, stop=stop, risk=0.5)
        m = metrics(eq, tr, res)
        if m["n_trades"] < 20:
            continue
        pnls = [t["pnl"] for t in tr]
        rng = np.random.default_rng(11)
        finals, sharpes, dds = [], [], []
        for _ in range(2000):
            boot = rng.choice(pnls, size=len(pnls), replace=True)
            c = equity_from_pnls(boot)
            finals.append(c.iloc[-1] - 1)
            sharpes.append(sharpe_from_curve(c, res))
            dds.append((c / c.cummax() - 1).min())
        f = np.array(finals)
        rows.append({"symbol": sym, "res": res, "trades": m["n_trades"],
                     "cagr": m["cagr"], "sharpe": m["sharpe"],
                     "win": m["win_rate"], "pf": m["profit_factor"],
                     "mc_median": float(np.median(f)),
                     "mc_p05": float(np.percentile(f, 5)),
                     "prob_loss": float((f <= 0).mean()),
                     "dd_worst": float(np.percentile(dds, 5))})
        print(f"{sym:7s} {res:3s} {m['n_trades']:6.0f} {m['cagr']*100:6.1f}% "
              f"{m['sharpe']:7.2f} {np.median(f)*100:6.1f}% "
              f"{np.percentile(f,5)*100:6.1f}% {(f<=0).mean()*100:7.1f}% "
              f"{np.percentile(dds,5)*100:7.1f}%")
    if rows:
        d = pd.DataFrame(rows)
        d.to_csv(os.path.join(HERE, "results", "smc_monte_carlo.csv"), index=False)
        print("\nwrote results/smc_monte_carlo.csv")
        print("\n=== comparison to the adx_trend baseline ===")
        print("  adx_trend BTC 4h   : Sharpe 0.79, 70 trades, P(loss) 28.2%, p5 -18.8%")
        print("  order block ETH 4h : Sharpe 1.01, 376 trades  <- more trades, "
              "similar Sharpe, 49% win rate (trend following needs few wins)")


if __name__ == "__main__":
    main()
