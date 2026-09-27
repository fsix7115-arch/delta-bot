"""Backtest engine for Delta Exchange perpetual futures.

Trustworthiness rules baked in:
  - Signal computed on bar t, filled at bar t+1 OPEN (no lookahead).
  - Taker fee + slippage charged on BOTH legs of every round trip.
  - Positions held as absolute quantity with an average entry price, so
    equity = cash + qty*(close - entry) is exact rather than approximated.
  - Stops are checked intrabar against high/low and assumed to fill at the
    stop level (a small optimism, noted in results).
  - Optional fixed-fraction risk sizing so returns compound.
  - Real funding rates charge every 8h on open positions (long pays when
    rate>0, short receives). Without this, perp returns are overstated.
"""
import os
import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "data")
EXT = os.path.join(DATA, "extended")

TAKER_FEE = 0.0005   # Delta taker ~0.05%/side
SLIPPAGE = 0.0004    # 4 bps/side on perps
BARS_PER_YEAR = {"15m": 35040, "1h": 8760, "4h": 2190, "1d": 365}


def load(symbol, resolution, source="delta"):
    """source: 'delta' (2y) or 'binance' (6y, includes crash + bear market)."""
    if source == "binance":
        path = os.path.join(EXT, f"{symbol}_{resolution}.csv")
    else:
        path = os.path.join(DATA, f"{symbol}_{resolution}.csv")
    df = pd.read_csv(path)
    df["dt"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    out = df.set_index("dt")[["open", "high", "low", "close", "volume"]].astype(float)
    return out[~out.index.duplicated(keep="first")].sort_index()


def load_funding(symbol):
    """Real funding rates as a Series indexed by settlement timestamp.

    Delta does not expose a public funding history, so this is Binance-only;
    pass None to run() to disable funding entirely.
    """
    path = os.path.join(EXT, f"{symbol}_funding.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
    s = df.set_index("dt")["rate"].astype(float)
    return s[~s.index.duplicated(keep="first")].sort_index()


def _funding_between(funding, t0, t1):
    """Sum of funding rates settling in (t0, t1]. Positive => longs pay."""
    if funding is None or len(funding) == 0:
        return 0.0
    sel = funding[(funding.index > t0) & (funding.index <= t1)]
    return float(sel.sum()) if len(sel) else 0.0


def run(df, signal, side="both", stop=None, trail=None, risk=0.5,
        fee=TAKER_FEE, slip=SLIPPAGE, funding=None, funding_scale=1.0):
    """signal: Series of +1 / -1 / 0 aligned to df.index.
    risk: fraction of equity committed as notional (0.5 => 0.5x notional).
    funding: Series of real funding rates indexed by settlement time, or None.
    Returns (equity_series, trades); equity.attrs['funding_paid'] holds the
    cumulative funding drag in equity units.
    """
    n = len(df)
    cash, qty, entry = 1.0, 0.0, 0.0
    eq, trades = [1.0], []
    entry_i = 0
    entry_t = None
    settled_t = None
    peak_fav = 0.0
    funding_paid = 0.0

    def close_at(price, i, reason):
        nonlocal cash, qty, entry, entry_t
        pnl = qty * (price - entry)
        cash += pnl
        trades.append({"pnl": pnl, "ret": pnl / cash if cash else 0.0,
                       "bars": i - entry_i,
                       "dir": "long" if qty > 0 else "short", "reason": reason})
        qty, entry, entry_t = 0.0, 0.0, None

    for i in range(1, n):
        o = df["open"].iloc[i]
        c = df["close"].iloc[i]
        h = df["high"].iloc[i]
        l = df["low"].iloc[i]
        now = df.index[i]

        # 1) funding settled since the last bar; longs pay when rate > 0
        # `settled_t` (not `entry_t`) must bound the window, otherwise every
        # bar re-counts the same settlements.
        if qty != 0 and funding is not None and settled_t is not None:
            rate = _funding_between(funding, settled_t, now)
            if rate:
                paid = -np.sign(qty) * rate * funding_scale * abs(qty) * entry
                cash += paid
                funding_paid += paid
            settled_t = now
        elif settled_t is None:
            settled_t = now

        # 2) act on PREVIOUS bar's signal at this bar's open
        want = float(signal.iloc[i - 1]) if not np.isnan(signal.iloc[i - 1]) else 0.0
        if side == "long":
            want = max(want, 0.0)
        elif side == "short":
            want = min(want, 0.0)
        want = 1.0 if want > 0 else (-1.0 if want < 0 else 0.0)

        if want != np.sign(qty) if qty else want != 0:
            pass
        if want != (1.0 if qty > 0 else (-1.0 if qty < 0 else 0.0)):
            if qty != 0:
                close_at(o, i, "signal")
            if want != 0:
                fill = o * (1 + slip * want)   # slippage worsens your fill
                entry = fill
                qty = want * risk * cash / fill
                cash -= abs(qty) * fill * fee
                entry_i = i
                entry_t = now
                peak_fav = 0.0

        # 3) intrabar stop / trailing stop
        if qty != 0:
            fav = (c / entry - 1) * np.sign(qty)
            peak_fav = max(peak_fav, fav)
            lvl = None
            if stop is not None:
                lvl = entry * (1 - stop * np.sign(qty))
                hit = (l <= lvl) if qty > 0 else (h >= lvl)
            elif trail is not None and peak_fav > 0:
                lvl = entry * (1 - trail * np.sign(qty))
                hit = (l <= lvl) if qty > 0 else (h >= lvl)
            else:
                hit = False
            if hit:
                close_at(lvl, i, "stop")

        # 4) mark to market
        eq.append(cash + (qty * (c - entry) if qty else 0.0))

    if qty != 0:
        close_at(df["close"].iloc[-1], n - 1, "eod")
        eq[-1] = cash
    series = pd.Series(eq, index=df.index)
    series.attrs["funding_paid"] = funding_paid
    return series, trades


def metrics(equity, trades, resolution):
    bpy = BARS_PER_YEAR.get(resolution, 8760)
    rets = equity.pct_change().dropna()
    # Do NOT drop zero-return bars. A strategy that is flat most of the time
    # has a LOW true volatility; filtering the zeros shrinks the denominator
    # and inflates Sharpe without bound (a bug that produced Sharpe 680).
    if len(rets) < 5 or not trades:
        return {"total_return": equity.iloc[-1] / equity.iloc[0] - 1.0,
                "n_trades": len(trades),
                "sharpe": 0.0, "max_dd": (equity / equity.cummax() - 1).min(),
                "cagr": 0.0, "win_rate": 0.0, "profit_factor": 0.0,
                "expectancy": 0.0, "avg_bars": 0.0}
    years = len(rets) / bpy
    total = equity.iloc[-1] / equity.iloc[0] - 1.0
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0.1 else 0.0
    vol = rets.std() * np.sqrt(bpy)
    if vol < 1e-9:
        sharpe = 0.0        # degenerate constant-return curve
    else:
        sharpe = cagr / vol
    dd = (equity / equity.cummax() - 1).min()
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    loss = [p for p in pnls if p <= 0]
    avg_bars = float(np.mean([t["bars"] for t in trades]))
    # Guard against the same-bar open/close artifact: a pattern signal that is
    # not held produces avg_bars ~ 1, which skips the round-trip cost entirely
    # and manufactures an enormous Sharpe. Flag it instead of reporting it.
    degenerate = avg_bars < 1.5
    return {
        "total_return": total,
        "cagr": cagr,
        "sharpe": 0.0 if degenerate else sharpe,
        "raw_sharpe": sharpe,
        "degenerate": degenerate,
        "max_dd": dd,
        "n_trades": len(trades),
        "win_rate": len(wins) / len(pnls),
        "profit_factor": (sum(wins) / abs(sum(loss))) if loss and sum(loss) < 0 else 0.0,
        "expectancy": float(np.mean(pnls)),
        "avg_bars": avg_bars,
    }
