"""Score the shadow log: were the signals any good?

The shadow log records what the strategy said at each 4h bar. On its own that
tells you nothing -- a signal that is always "long" is a signal, and a useless
one. The only question worth asking is whether it would have made money.

This replays the logged signals forward against the actual candles and reports
the same metrics the backtester uses, so shadow mode and backtest can be
compared directly. It also reports a deliberately naive baseline (always long)
because "did better than doing nothing" is a much lower bar than "is good".

No lookahead: a signal logged at bar T is only ever applied from bar T+1
onward, matching engine.run.
"""
import json
import os
import sys
from collections import defaultdict

import pandas as pd

from engine import load

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "results", "shadow_log.jsonl")
HOLD = 8          # bars, must match shadow.py's hold_bars
STOP = 0.02       # must match shadow.py's STOP_PCT
SYMBOL, RESOLUTION = "ETHUSD", "4h"


def load_log(path=LOG):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "signal" in d and "bar_time" in d:
                rows.append(d)
    rows.sort(key=lambda d: d["ts"])
    return rows


def load_bars(symbol, res, source="delta"):
    return load(symbol, res, source=source)


def simulate(signals, df, hold=HOLD, stop=STOP):
    """Apply logged signals to bars, entering on the bar AFTER the signal.

    Returns a list of round trips. Deliberately simple: no partial exits, no
    trailing stop, just signal -> max(hold bars, stop hit).
    """
    sig_at = {}
    for s in signals:
        t = pd.Timestamp(s["bar_time"])
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        sig_at[t] = int(s["signal"])

    idx = df.index
    trades, i = [], 0
    while i < len(idx) - 1:
        t = idx[i]
        if t not in sig_at or sig_at[t] == 0:
            i += 1
            continue
        side = sig_at[t]
        entry = float(df["open"].iloc[i + 1])
        if not entry or entry != entry:
            i += 1
            continue
        stop_px = entry * (1 - stop) if side > 0 else entry * (1 + stop)
        exit_px, reason, bars = None, "hold", 0
        for j in range(i + 1, min(i + 1 + hold, len(idx))):
            bars += 1
            lo, hi = float(df["low"].iloc[j]), float(df["high"].iloc[j])
            if side > 0 and lo <= stop_px:
                exit_px, reason = stop_px, "stop"
                break
            if side < 0 and hi >= stop_px:
                exit_px, reason = stop_px, "stop"
                break
        if exit_px is None:
            exit_px = float(df["close"].iloc[j - 1])
        trades.append({
            "entry_time": idx[i + 1], "side": side, "entry": entry,
            "exit": exit_px, "bars": bars, "reason": reason,
            "ret": (exit_px - entry) / entry * side,
        })
        i += bars + 1
    return trades


def stats(trades, label):
    if not trades:
        print(f"{label:22s} no trades")
        return None
    rets = [t["ret"] for t in trades]
    win = [r for r in rets if r > 0]
    lose = [r for r in rets if r <= 0]
    tot = sum(rets)
    peak, dd = 0.0, 0.0
    eq = 0.0
    for r in rets:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    row = {
        "label": label, "n": len(rets),
        "win": len(win) / len(rets) * 100,
        "avg": tot / len(rets) * 100,
        "total": tot * 100,
        "dd": dd * 100,
        "avg_bars": sum(t["bars"] for t in trades) / len(rets),
        "stops": sum(1 for t in trades if t["reason"] == "stop"),
    }
    print(f"{row['label']:22s} n={row['n']:3d}  win {row['win']:4.0f}%  "
          f"avg {row['avg']:+5.2f}%  total {row['total']:+6.2f}%  "
          f"worstDD {row['dd']:5.2f}%  bars {row['avg_bars']:.1f}  "
          f"stops {row['stops']}/{row['n']}")
    return row


def baseline(df, hold=HOLD, stop=STOP):
    """Always long, same exit rules. Deliberately the weakest thing that works."""
    sigs = [{"bar_time": str(df.index[i]), "signal": 1}
            for i in range(0, len(df) - hold - 1, hold + 1)]
    return simulate(sigs, df, hold, stop)


def main():
    rows = load_log()
    if not rows:
        print("no shadow entries yet -- run shadow.py first")
        return
    sym = rows[-1].get("symbol", "ETHUSD")
    res = rows[-1].get("res", "4h")
    print(f"log entries: {len(rows)}  ({rows[0]['ts'][:16]} -> {rows[-1]['ts'][:16]})")
    print(f"signal mix: {dict((k, sum(1 for r in rows if r['signal']==k)) for k in (1,0,-1))}")
    print(f"pair: {sym} {res}\n")

    df = load(SYMBOL, RESOLUTION, source="delta")
    # If the cached candles are older than the bar the log expects, refresh
    # before scoring. Otherwise the replay window is silently empty and every
    # result reads as "no trades", which looks like a strategy failure.
    if rows:
        first = pd.Timestamp(rows[0]["bar_time"])
        if first.tzinfo is None:
            first = first.tz_localize("UTC")
        if df.index[-1] < first:
            print("cached candles are stale, refetching...")
            os.system(f"{sys.executable} {os.path.abspath(__file__).replace('shadow_score.py', 'fetch_data.py')} >/dev/null 2>&1")
            df = load_bars(sym, res)
    first = pd.Timestamp(rows[0]["bar_time"])
    if first.tzinfo is None:
        first = first.tz_localize("UTC")
    df = df[df.index >= first]
    print(f"bars since first signal: {len(df)}\n")

    trades = simulate(rows, df)
    print("=== shadow signals, scored ===")
    got = stats(trades, "strategy")
    stats(baseline(df), "baseline (always long)")

    if got and got["total"] > 0:
        print("\nsignals are ahead over this window")
    elif got:
        print("\nsignals are behind over this window")
    print(f"\nNOTE: {len(rows)} log entries is a very small sample."
          f"\n      Shadow mode only accumulates 6 entries a day."
          f"\n      Judge nothing until there are 30+ entries.")


if __name__ == "__main__":
    main()
