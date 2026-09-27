"""Restrict trading to the hours where price actually moves, and re-test.

tod_profile.py found that 13:00-16:00 UTC is the highest-activity window on
both BTC and ETH, and that the ranking held across a 50/50 split of a 2.7-year
dataset. BTC's best hour still has a median move below the 0.18% round trip;
ETH's clears it.

That measures movement, not tradeability. A window where price moves more is
also a window where stops get hit wider, so the correct test is to run the
strategy on 15m bars with signals suppressed outside the window and compare
against the all-hours baseline from sweep_intraday.py.

Three variants, because the honest comparison is not obvious:
  - all hours (baseline)
  - entries allowed only in the window
  - entries allowed only outside it  (if this wins, the finding is inverted)

Reporting gross alongside net again, since the whole intraday question is
whether a venue problem is masking a real edge.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import strategies_smc as M
import strategies_v2 as V2
from engine import load, run, metrics

SENT = os.path.join(HERE, "data", "sentiment", "fear_greed.csv")
IS_FRAC = 0.55
OUT = os.path.join(HERE, "results", "tod_window.csv")

# 13:00-16:59 UTC inclusive, from tod_profile.py's out-of-sample-validated window
WIN_LO, WIN_HI = 13, 16


def main():
    src = os.environ.get("SOURCE", "delta")
    sent = V2.load_sentiment(SENT)
    rows = []

    for sym in ("ETHUSD", "BTCUSD"):
        df = load(sym, "15m", source=src)
        if len(df) < 5000:
            print(f"skip {sym}: {len(df)} bars")
            continue
        oos = df.iloc[int(len(df) * IS_FRAC):]
        base = M.order_block_trade(oos, impulse_atr=1.0, max_age=8, hold_bars=8)
        fng = V2._sentiment_at(sent, oos.index)
        avg = fng.rolling(5, min_periods=1).mean().shift(1)
        gated = pd.Series(np.where((avg < 20) | (avg > 80), 0.0, base),
                          index=oos.index)

        h = oos.index.hour
        in_win = (h >= WIN_LO) & (h <= WIN_HI)
        print(f"\n=== {sym} 15m  OOS {len(oos):,} bars  "
              f"window {WIN_LO:02d}:00-{WIN_HI:02d}:59 UTC "
              f"({in_win.mean()*100:.0f}% of bars) ===", flush=True)
        print(f"{'variant':<22s} {'sharpe':>7s} {'2x':>6s} {'gross':>8s} "
              f"{'net':>8s} {'trades':>7s} {'win':>5s} {'pf':>5s}", flush=True)

        variants = {
            "all hours": gated,
            f"window {WIN_LO}-{WIN_HI} only": gated.where(in_win, 0.0),
            "outside window only": gated.where(~in_win, 0.0),
        }
        for name, sig in variants.items():
            eq, tr = run(oos, sig, stop=0.004, risk=0.5)
            m = metrics(eq, tr, "15m")
            m2 = metrics(*run(oos, sig, stop=0.004, risk=0.5,
                              fee=0.001, slip=0.0008), "15m")
            eq0, _ = run(oos, sig, stop=0.004, risk=0.5, fee=0.0, slip=0.0)
            gross = (eq0.iloc[-1] - 1) * 100
            rows.append({"symbol": sym, "variant": name, "sharpe": m["sharpe"],
                         "sharpe_2x": m2["sharpe"], "gross_pct": gross,
                         "net_pct": m["total_return"] * 100,
                         "trades": m["n_trades"], "win": m["win_rate"] * 100,
                         "pf": m["profit_factor"], "max_dd": m["max_dd"] * 100})
            r = rows[-1]
            print(f"{name:<22s} {m['sharpe']:>7.2f} {m2['sharpe']:>6.2f} "
                  f"{gross:>+7.2f}% {m['total_return']*100:>+7.2f}% "
                  f"{m['n_trades']:>7d} {m['win_rate']*100:>4.0f}% "
                  f"{m['profit_factor']:>5.2f}", flush=True)

    if not rows:
        return
    d = pd.DataFrame(rows)
    d.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}")
    print(f"""
INTERPRETING THIS

A time window is only useful if it improves the ratio of edge to cost, not
just the number of moves. Watch two things:
  - gross up AND net up together  -> the window genuinely helps
  - gross up, net unchanged      -> more movement, same fee bill, no gain
  - both negative                -> the movement is noise, and 13:00-16:00 is
                                    just when the market is busy

The "outside window only" row is the sanity check. If restricting trades to the
dead hours beats restricting them to the peak hours, the time-of-day story is
backwards and should be discarded rather than reframed.
""")


if __name__ == "__main__":
    main()
