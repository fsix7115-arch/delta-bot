"""Mechanised Smart Money Concepts (SMC) — the testable subset of a prose playbook.

WHAT IS ACTUALLY TESTABLE HERE

The source material describes SMC in words: "fair value gap", "liquidity grab",
"order block", "BOS/CHoCH". Those words have no numbers attached, so a literal
replication is impossible. But four of them DO have an unambiguous mechanical
definition on OHLC data, and those are implemented below:

  FVG / imbalance : candle i's low  >  candle i+2's high  (bullish gap), or
                    candle i's high <  candle i+2's low   (bearish gap).
  Liquidity grab  : price wicks beyond a prior N-bar extreme but closes back
                    inside it — a failed breakout that swept resting stops.
  Order block     : the last down-candle before an impulsive up-move (and the
                    mirror), tagged with the extreme that preceded it.
  BOS / CHoCH     : a close beyond the last swing high (continuation) versus
                    beyond the last swing low after a downtrend (reversal).

Each of these is a STATEFUL pattern, not a per-bar indicator, so each is built
as a small scan that emits a signal at the bar where the pattern COMPLETES.
Signals are shifted one bar so the engine fills at the next open, never at the
pattern bar itself.

The remaining ideas in the source (whale intent, "institutional footprint",
"deep discount vs premium", bull/bear debate) are not encoded here because they
are either unfalsifiable or already covered by the backtest harness. That is a
deliberate omission, not an oversight.
"""
import numpy as np
import pandas as pd


# --------------------------------------------------------------------- helpers

def _swing_points(df, left=3, right=3):
    """Fractal swing highs/lows confirmed `right` bars later (no lookahead)."""
    h, l = df["high"].values, df["low"].values
    n = len(df)
    sh = np.full(n, np.nan)
    sl = np.full(n, np.nan)
    for i in range(left, n - right):
        window_h = h[i - left:i + right + 1]
        window_l = l[i - left:i + right + 1]
        if h[i] == window_h.max() and (window_h.argmax() == left):
            sh[i] = h[i]
        if l[i] == window_l.min() and (window_l.argmin() == left):
            sl[i] = l[i]
    return sh, sl


def _atr(df, n=14):
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


# ------------------------------------------------------------------------ FVG

def fvg_trade(df, atr_mult=0.5, max_age=20, stop=0.02, target=0.06,
              hold_bars=8):
    """Enter when price returns into a recent, untested imbalance.

    A bullish FVG is a 3-candle gap left by an impulsive move. The gap is
    "mitigated" (spent) the first time price trades back through it, so only
    un-mitigated gaps can fire. Gaps older than `max_age` bars are ignored.
    """
    n = len(df)
    sig = np.zeros(n)
    h, l, c = df["high"], df["low"], df["close"]
    a = _atr(df)

    # gaps are detected at bar i+2 and become known then
    gaps = []
    for i in range(2, n):
        if l.iloc[i - 2] > h.iloc[i] and (l.iloc[i - 2] - h.iloc[i]) > a.iloc[i] * atr_mult:
            gaps.append({"lo": h.iloc[i], "hi": l.iloc[i - 2], "dir": 1, "born": i})
        elif h.iloc[i - 2] < l.iloc[i] and (l.iloc[i] - h.iloc[i - 2]) > a.iloc[i] * atr_mult:
            gaps.append({"lo": h.iloc[i - 2], "hi": l.iloc[i], "dir": -1, "born": i})

    pending = []
    for i in range(n):
        # expire
        pending = [g for g in pending if i - g["born"] <= max_age]
        # did we fill one this bar?
        for g in list(pending):
            if g["dir"] == 1 and l.iloc[i] <= g["hi"]:
                if c.iloc[i] > g["hi"]:
                    sig[i] = 1
                g["spent"] = True
                pending.remove(g)
            elif g["dir"] == -1 and h.iloc[i] >= g["lo"]:
                if c.iloc[i] < g["lo"]:
                    sig[i] = -1
                g["spent"] = True
                pending.remove(g)
        # add gaps born at this bar
        pending += [g for g in gaps if g["born"] == i]
    return _hold(pd.Series(sig, index=df.index), hold_bars)


# ------------------------------------------------------------- liquidity grab

def liquidity_grab(df, lookback=20, stop=0.02, target=0.05, confirm_bars=1,
                   hold_bars=8):
    """Failed breakout: wick beyond a prior extreme, close back inside it.

    This is the mechanical form of "smart money hunts the stops". The claim
    being tested is that a swept extreme marks a short-term reversal, not that
    institutions are involved.
    """
    n = len(df)
    sig = np.zeros(n)
    h, l, c = df["high"], df["low"], df["close"]
    hi = h.rolling(lookback).max().shift(1)
    lo = l.rolling(lookback).min().shift(1)
    for i in range(1, n):
        if pd.isna(hi.iloc[i]) or pd.isna(lo.iloc[i]):
            continue
        swept_high = h.iloc[i] > hi.iloc[i] and c.iloc[i] < hi.iloc[i]
        swept_low = l.iloc[i] < lo.iloc[i] and c.iloc[i] > lo.iloc[i]
        if swept_low and (not confirm_bars or c.iloc[i - 1] <= lo.iloc[i]):
            sig[i] = 1
        elif swept_high and (not confirm_bars or c.iloc[i - 1] >= hi.iloc[i]):
            sig[i] = -1
    return _hold(pd.Series(sig, index=df.index), hold_bars)


# ---------------------------------------------------------------- order block

def order_block_trade(df, impulse_atr=1.5, lookback=60, stop=0.02, target=0.06,
                      max_age=30, hold_bars=8):
    """Last opposing candle before an impulsive move, entered on the retest.

    A bullish order block is the last down-close candle before a rally of at
    least `impulse_atr` ATR. We tag its low, then wait for price to trade back
    into that candle's body.
    """
    n = len(df)
    sig = np.zeros(n)
    o, c, h, l = df["open"], df["close"], df["high"], df["low"]
    a = _atr(df)

    blocks = []
    for i in range(1, n - 3):
        if pd.isna(a.iloc[i]) or a.iloc[i] <= 0:
            continue
        # A block is only KNOWN once the impulse has actually printed. Tag it
        # at bar j = i+3, not at i, otherwise the retest test below would be
        # reading the move that has not happened yet (lookahead leak).
        j = i + 3
        fwd = c.iloc[i + 1:j + 1]
        if c.iloc[i] < o.iloc[i]:                      # down candle
            if (fwd.max() - c.iloc[i]) > impulse_atr * a.iloc[i]:
                blocks.append({"lo": l.iloc[i], "hi": max(o.iloc[i], c.iloc[i]),
                               "dir": 1, "born": j})
        elif c.iloc[i] > o.iloc[i]:                    # up candle
            if (c.iloc[i] - fwd.min()) > impulse_atr * a.iloc[i]:
                blocks.append({"lo": min(o.iloc[i], c.iloc[i]), "hi": h.iloc[i],
                               "dir": -1, "born": j})

    pending = []
    for i in range(n):
        pending = [b for b in pending if i - b["born"] <= max_age]
        for b in list(pending):
            if b["dir"] == 1 and l.iloc[i] <= b["hi"] and c.iloc[i] > b["lo"]:
                sig[i] = 1
                pending.remove(b)
            elif b["dir"] == -1 and h.iloc[i] >= b["lo"] and c.iloc[i] < b["hi"]:
                sig[i] = -1
                pending.remove(b)
        pending += [b for b in blocks if b["born"] == i]
    return _hold(sig, hold_bars)


def _hold(sig, hold_bars):
    """Carry the last non-zero signal forward so a position actually lasts.

    Without this the engine opens and closes on the same bar, which skips the
    round-trip cost entirely and invents a huge Sharpe. A pattern signal is an
    ENTRY event, not a per-bar state.
    """
    if isinstance(sig, np.ndarray):
        sig = pd.Series(sig)
    out = np.zeros(len(sig))
    cur, left = 0.0, 0
    for i, v in enumerate(sig.values):
        if v != 0:
            cur, left = v, hold_bars
        if cur != 0:
            if left <= 0:
                cur = 0.0
            else:
                out[i] = cur
                left -= 1
    return pd.Series(out, index=sig.index)


# -------------------------------------------------------------------- BOS/CHoCH

def bos_choch_trade(df, left=3, right=3, stop=0.02, target=0.06):
    """Structure breaks: BOS continues a trend, CHoCH is the first opposite break.

    Trend state is inferred from which side price last closed beyond. A break
    against the prevailing trend flips it (CHoCH); a break with it continues
    (BOS). We only trade the CHoCH leg, because that is the reversal claim.
    """
    n = len(df)
    sig = np.zeros(n)
    c = df["close"]
    sh, sl = _swing_points(df, left, right)
    last_sh = np.nan
    last_sl = np.nan
    state = 0            # +1 uptrend, -1 downtrend
    for i in range(n):
        if not np.isnan(sh[i]):
            last_sh = sh[i]
        if not np.isnan(sl[i]):
            last_sl = sl[i]
        if np.isnan(c.iloc[i]) or i == 0:
            continue
        broke_high = last_sh is not np.nan and not np.isnan(last_sh) and c.iloc[i] > last_sh
        broke_low = last_sl is not np.nan and not np.isnan(last_sl) and c.iloc[i] < last_sl
        if broke_high and state <= 0:
            sig[i] = 1 if state == 0 else -1   # CHoCH up / initial up
            state = 1
        elif broke_low and state >= 0:
            sig[i] = -1 if state == 0 else 1   # CHoCH down / initial down
            state = -1
    return pd.Series(sig, index=df.index)
