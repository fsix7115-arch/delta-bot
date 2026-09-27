"""Parallel walk-forward sweep. Writes one CSV, prints a ranked summary.

Protocol per config:
  - 3y of data, first 55% IS (pick), last 45% OOS (report)
  - OOS also re-run at 2x fees+slippage to test cost robustness
Promotion bar: OOS Sharpe > 0.5, stress Sharpe > 0, OOS trades >= 15.
"""
import itertools
import os
import os.path
import pandas as pd
from concurrent.futures import ProcessPoolExecutor

import strategies as S
from engine import load, run, metrics, load_funding

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
IS_FRAC = 0.55

STRATS = [
    S.s_ema_cross(9, 21), S.s_ema_cross(20, 50), S.s_ema_cross(50, 200),
    S.s_trend_rsi(20, 50, 14, 40, 60), S.s_trend_rsi(50, 200, 14, 45, 55),
    S.s_breakout(20), S.s_breakout(55), S.s_breakout(100),
    S.s_macd(), S.s_donchian_trend(20, 100), S.s_donchian_trend(55, 200),
    S.s_atr_breakout(20, 50), S.s_atr_breakout(55, 100),
    S.s_mean_revert(50, 1.5), S.s_mean_revert(100, 2.0),
    S.s_rsi_revert(50, 14, 30, 70),
    S.s_adx_trend(20, 50, 14, 20), S.s_adx_trend(50, 200, 14, 25),
    S.s_vol_regime_breakout(20, 50), S.s_vol_regime_breakout(55, 100),
]
STOPS = [None, 0.02, 0.035]
SYMBOLS = ["BTCUSD", "ETHUSD"]
RESOLUTIONS = ["1h", "4h", "1d"]


def evaluate(task):
    sym, res, sidx, stop, source = task
    strat = STRATS[sidx]
    df = load(sym, res, source=source)
    funding = load_funding(sym) if source == "binance" else None
    split = int(len(df) * IS_FRAC)
    isdf, oosdf = df.iloc[:split], df.iloc[split:]
    isig, osig = strat(isdf), strat(oosdf)
    iseq, itr = run(isdf, isig, stop=stop, risk=0.5, funding=funding)
    im = metrics(iseq, itr, res)
    if not itr or im["n_trades"] < 8:
        return None
    oeq, otr = run(oosdf, osig, stop=stop, risk=0.5, funding=funding)
    om = metrics(oeq, otr, res)
    # same OOS window with funding switched off, to isolate its contribution
    nfeq, nftr = run(oosdf, osig, stop=stop, risk=0.5, funding=None)
    nfm = metrics(nfeq, nftr, res)
    seq, str_ = run(oosdf, osig, stop=stop, risk=0.5, fee=0.001, slip=0.0008,
                    funding=funding)
    sm = metrics(seq, str_, res)
    return {
        "symbol": sym, "res": res, "strategy": strat.__name__, "stop": stop,
        "is_sharpe": im["sharpe"], "is_cagr": im["cagr"], "is_dd": im["max_dd"],
        "is_trades": im["n_trades"],
        "oos_sharpe": om["sharpe"], "oos_cagr": om["cagr"], "oos_dd": om["max_dd"],
        "oos_trades": om["n_trades"], "oos_win": om["win_rate"],
        "oos_pf": om["profit_factor"], "oos_ret": om["total_return"],
        "stress_sharpe": sm["sharpe"], "stress_cagr": sm["cagr"],
        "nofund_sharpe": nfm["sharpe"], "nofund_cagr": nfm["cagr"],
        "funding_drag": nfm["cagr"] - om["cagr"],
    }


def main():
    os.makedirs(RESULTS, exist_ok=True)
    source = os.environ.get("SOURCE", "binance")
    out_name = "sweep_6y.csv" if source == "binance" else "sweep.csv"
    # Cheaper timeframes first so partial progress is still useful.
    res_list = os.environ.get("RESOLUTIONS", "4h,1d,1h").split(",")
    tasks = list(itertools.product(SYMBOLS, res_list,
                                  range(len(STRATS)), STOPS, [source]))
    print(f"evaluating {len(tasks)} configs on {os.cpu_count()} workers "
          f"(source={source}, res={res_list})", flush=True)
    rows = []
    done = 0
    with ProcessPoolExecutor(max_workers=max(2, os.cpu_count() - 1)) as ex:
        for r in ex.map(evaluate, tasks, chunksize=2):
            done += 1
            if r:
                rows.append(r)
            if done % 10 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} configs done", flush=True)
    df = pd.DataFrame(rows).sort_values("oos_sharpe", ascending=False)
    out = os.path.join(RESULTS, out_name)
    df.to_csv(out, index=False)
    print(f"\nwrote {out}  ({len(df)} rows)\n")
    print("TOP 15 BY OOS SHARPE")
    print(df.head(15).to_string(index=False))
    ok = df[(df.oos_sharpe > 0.5) & (df.stress_sharpe > 0) & (df.oos_trades >= 15)]
    print(f"\nPASSED bar: {len(ok)} / {len(df)}")
    if len(ok):
        print(ok.head(20).to_string(index=False))
    for sym in SYMBOLS:
        for res in res_list:
            dfx = load(sym, res, source=source)
            oos = dfx.iloc[int(len(dfx) * IS_FRAC):]
            bh = oos["close"].iloc[-1] / oos["close"].iloc[0] - 1
            bpy = {"1h": 8760, "4h": 2190, "1d": 365}[res]
            cagr = (1 + bh) ** (bpy / max(len(oos), 1)) - 1
            print(f"BH {sym} {res}: OOS {bh*100:7.1f}%  cagr {cagr*100:6.1f}%")


if __name__ == "__main__":
    main()
