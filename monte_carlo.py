"""Monte Carlo robustness test for a chosen strategy.

Question: is the backtest result an artefact of the exact sequence of trades
that happened, or would the strategy still be viable if the same trades had
arrived in a different order? A strategy that only wins in one specific order
is usually overfit.

Method: draw trade P&L from the empirical set WITH replacement (bootstrap),
rebuild an equity curve under the same risk fraction, and measure drawdown and
Sharpe across many shuffles. Reports the full distribution, not just a mean.
"""
import os
import numpy as np
import pandas as pd

import strategies as S
from engine import load, run, metrics, BARS_PER_YEAR

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
IS_FRAC = 0.55


def equity_from_pnls(pnls, risk=0.5, start=1.0):
    """Rebuild an equity curve from a sequence of fractional trade P&Ls."""
    eq, cur = [start], start
    for p in pnls:
        cur *= (1 + p)
        eq.append(cur)
    return pd.Series(eq)


def sharpe_from_curve(eq, res):
    r = eq.pct_change().dropna()
    r = r[r != 0]
    if len(r) < 5:
        return 0.0
    bpy = BARS_PER_YEAR[res]
    years = max(len(r) / bpy, 1e-6)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1
    vol = r.std() * np.sqrt(bpy)
    return 0.0 if vol < 1e-12 else cagr / vol


def test_config(sym, res, strat, stop, iters=2000, seed=7):
    df = load(sym, res, source="delta")
    oos = df.iloc[int(len(df) * IS_FRAC):]
    sig = strat(oos)
    eq, tr = run(oos, sig, stop=stop, risk=0.5)
    m = metrics(eq, tr, res)
    pnls = [t["pnl"] for t in tr]
    if len(pnls) < 10:
        return None

    rng = np.random.default_rng(seed)
    finals, sharpes, dds, maxdds = [], [], [], []
    for _ in range(iters):
        boot = rng.choice(pnls, size=len(pnls), replace=True)
        c = equity_from_pnls(boot)
        finals.append(c.iloc[-1] - 1)
        sharpes.append(sharpe_from_curve(c, res))
        dds.append(c.iloc[-1] / c.cummax().max() - 1)
        maxdds.append((c / c.cummax() - 1).min())

    finals = np.array(finals)
    return {
        "symbol": sym, "res": res, "stop": stop, "strategy": strat.__name__,
        "n_trades": len(pnls), "actual_cagr": m["cagr"], "actual_sharpe": m["sharpe"],
        "actual_dd": m["max_dd"], "win_rate": m["win_rate"],
        "pf": m["profit_factor"],
        "mc_median": float(np.median(finals)),
        "mc_mean": float(finals.mean()),
        "mc_p05": float(np.percentile(finals, 5)),
        "mc_p25": float(np.percentile(finals, 25)),
        "mc_p75": float(np.percentile(finals, 75)),
        "mc_p95": float(np.percentile(finals, 95)),
        "prob_loss": float((finals <= 0).mean()),
        "prob_halved": float((finals <= -0.5).mean()),
        "sharpe_p05": float(np.percentile(sharpes, 5)),
        "sharpe_median": float(np.median(sharpes)),
        "dd_median": float(np.median(maxdds)),
        "dd_worst": float(np.percentile(maxdds, 5)),
    }


def main():
    configs = [
        ("BTCUSD", "4h", S.s_adx_trend(20, 50, 14, 20), None),
        ("BTCUSD", "4h", S.s_adx_trend(20, 50, 14, 20), 0.02),
        ("BTCUSD", "1d", S.s_adx_trend(20, 50, 14, 20), 0.035),
        ("ETHUSD", "4h", S.s_adx_trend(20, 50, 14, 20), None),
        ("BTCUSD", "4h", S.s_donchian_trend(55, 200), None),
        ("ETHUSD", "4h", S.s_donchian_trend(55, 200), 0.035),
    ]
    rows = []
    print("Monte Carlo: 2000 bootstraps of the OOS trade P&L sequence\n")
    for sym, res, strat, stop in configs:
        r = test_config(sym, res, strat, stop)
        if r is None:
            print(f"{sym} {res} stop={stop}: too few trades")
            continue
        rows.append(r)
        print(f"{sym:7s} {res:3s} stop={str(stop):5s} {r['n_trades']:4d} trades | "
              f"actual CAGR {r['actual_cagr']*100:6.1f}% | "
              f"MC median {r['mc_median']*100:6.1f}% "
              f"[p5 {r['mc_p05']*100:6.1f}% .. p95 {r['mc_p95']*100:6.1f}%] | "
              f"P(loss) {r['prob_loss']*100:5.1f}% | "
              f"worst DD {r['dd_worst']*100:6.1f}%")

    if rows:
        d = pd.DataFrame(rows).sort_values("mc_median", ascending=False)
        d.to_csv(os.path.join(RES, "monte_carlo.csv"), index=False)
        print("\nwrote results/monte_carlo.csv")
        print("\n=== robustness read ===")
        for _, r in d.iterrows():
            verdict = ("ROBUST" if (r["prob_loss"] < 0.1 and r["mc_p05"] > 0)
                       else "MARGINAL" if r["prob_loss"] < 0.3
                       else "FRAGILE")
            print(f"{r['symbol']:7s} {r['res']:3s} stop={str(r['stop']):5s} "
                  f"P(loss)={r['prob_loss']*100:5.1f}%  "
                  f"p5={r['mc_p05']*100:6.1f}%  {verdict}")


if __name__ == "__main__":
    main()
