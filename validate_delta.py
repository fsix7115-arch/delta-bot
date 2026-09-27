"""Delta cross-validation of the chosen strategy.

IMPORTANT — read before trusting the output:

Delta only serves ~2 years of candles. That window (2024-09 -> 2026-09) sits
INSIDE the out-of-sample window of the 6y Binance sweep, so this is NOT an
independent out-of-sample test. It answers a narrower question: does the same
rule, applied to Delta's own price series and Delta's own fee/slippage
assumptions, produce a similar equity curve? Agreement raises confidence that
the result is not a Binance-specific artefact; it cannot prove the strategy is
live-ready.

Funding is unavailable (Delta exposes no public funding history), so the
per-funding drag measured from Binance is applied as a flat annual haircut on
the Delta run, and the unhedged run is printed alongside for comparison.
"""
import os
import numpy as np
import pandas as pd

import strategies as S
from engine import load, run, metrics

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
IS_FRAC = 0.55
# Annual funding drag measured on the 6y Binance run for this config.
FUNDING_HAIRCUT = {"ETHUSD": 0.017, "BTCUSD": 0.018}

CONFIGS = [
    ("ETHUSD", "4h", S.s_adx_trend(20, 50, 14, 20), None),
    ("ETHUSD", "4h", S.s_adx_trend(20, 50, 14, 20), 0.02),
    ("BTCUSD", "4h", S.s_adx_trend(20, 50, 14, 20), None),
    ("BTCUSD", "4h", S.s_adx_trend(20, 50, 14, 20), 0.02),
    ("ETHUSD", "1d", S.s_adx_trend(20, 50, 14, 20), 0.035),
    ("BTCUSD", "1d", S.s_adx_trend(20, 50, 14, 20), 0.035),
]


def bh_baseline(df, res):
    split = int(len(df) * IS_FRAC)
    oos = df.iloc[split:]
    total = oos["close"].iloc[-1] / oos["close"].iloc[0] - 1
    bpy = {"1h": 8760, "4h": 2190, "1d": 365}[res]
    cagr = (1 + total) ** (bpy / max(len(oos), 1)) - 1
    return total, cagr


def main():
    rows = []
    print(f"{'sym':8s} {'res':4s} {'stop':6s} {'sharpe':>7s} {'cagr':>7s} "
          f"{'dd':>7s} {'trades':>6s} {'pf':>6s} {'stress':>7s} "
          f"{'net_fund':>8s} {'BH_cagr':>8s}")
    for sym, res, strat, stop in CONFIGS:
        df = load(sym, res, source="delta")
        split = int(len(df) * IS_FRAC)
        isdf, oosdf = df.iloc[:split], df.iloc[split:]
        isig, osig = strat(isdf), strat(oosdf)

        iseq, itr = run(isdf, isig, stop=stop, risk=0.5)
        im = metrics(iseq, itr, res)
        if not itr or im["n_trades"] < 5:
            print(f"{sym:8s} {res:4s} {str(stop):6s}  -- too few IS trades --")
            continue

        oeq, otr = run(oosdf, osig, stop=stop, risk=0.5)
        om = metrics(oeq, otr, res)
        seq, str_ = run(oosdf, osig, stop=stop, risk=0.5, fee=0.001, slip=0.0008)
        sm = metrics(seq, str_, res)

        # flat annual funding haircut as a multiplicative drag on OOS growth
        years = len(oeq) / {"1h": 8760, "4h": 2190, "1d": 365}[res]
        net_cagr = (1 + om["cagr"]) / (1 + FUNDING_HAIRCUT[sym] * years) - 1
        _, bh = bh_baseline(df, res)

        rows.append({
            "symbol": sym, "res": res, "stop": stop,
            "is_sharpe": im["sharpe"], "is_trades": im["n_trades"],
            "oos_sharpe": om["sharpe"], "oos_cagr": om["cagr"],
            "oos_dd": om["max_dd"], "oos_trades": om["n_trades"],
            "oos_pf": om["profit_factor"], "oos_win": om["win_rate"],
            "stress_sharpe": sm["sharpe"],
            "net_funding_cagr": net_cagr, "bh_cagr": bh,
            "alpha_vs_bh": net_cagr - bh,
        })
        print(f"{sym:8s} {res:4s} {str(stop):6s} {om['sharpe']:7.2f} "
              f"{om['cagr']*100:6.1f}% {om['max_dd']*100:6.1f}% "
              f"{om['n_trades']:6d} {om['profit_factor']:6.2f} "
              f"{sm['sharpe']:7.2f} {net_cagr*100:7.1f}% {bh*100:7.1f}%")

    if rows:
        d = pd.DataFrame(rows).sort_values("oos_sharpe", ascending=False)
        d.to_csv(os.path.join(RES, "delta_validate.csv"), index=False)
        print("\nwrote results/delta_validate.csv")
        print("\nDelta window:", "2024-09 -> 2026-09 (subset of the Binance OOS window)")
        best = d.iloc[0]
        print(f"\nbest: {best.symbol} {best.res} stop={best.stop}")
        print(f"  OOS Sharpe {best.oos_sharpe:.2f} over {int(best.oos_trades)} trades")
        print(f"  CAGR {best.oos_cagr*100:.1f}% (net of funding est. "
              f"{best.net_funding_cagr*100:.1f}%) vs buy-hold {best.bh_cagr*100:.1f}%")
        print(f"  alpha vs buy-hold: {best.alpha_vs_bh*100:+.1f}%/yr")


if __name__ == "__main__":
    main()
