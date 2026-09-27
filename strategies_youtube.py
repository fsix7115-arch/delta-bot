"""Candle-break + liquidity-sweep strategy, mechanised from a YouTube walkthrough.

IMPORTANT — provenance and honesty:

This is an INTERPRETATION, not a replication. The source describes a
discretionary process ("character change", "body low break", "wick sweep",
judgement about which swing high to target) and never states numeric rules. The
rules below are a mechanical reading of that description:

  Entry (long): a candle closes beyond the previous candle's high, that candle
                is "fresh" (its high is not the range extreme of the last
                `fresh_n` candles), and it broke the body low on entry.
  Stop:       `sl_mult` x the sweep candle's body (the risk unit).
  Target:     the next swing high (`target_mult` x risk), i.e. a 1:5 style
              partial-friendly payoff.
  Exit:       target hit, stop hit, or a `max_bars` time stop.

A discretionary trader also applies judgement we cannot encode. So treat any
result as a lower bound on the idea's viability, and as evidence about whether
the pattern exists and is tradeable after costs -- not as the strategy itself.

All indicators are shifted one bar: a signal may only use information that was
available before the bar it trades.
"""
import numpy as np
import pandas as pd


def _swing_high(df, lookback, shift=1):
    return df["high"].rolling(lookback).max().shift(shift)


def _swing_low(df, lookback, shift=1):
    return df["low"].rolling(lookback).min().shift(shift)


def candle_break(df, lookback=20, sl_mult=1.0, target_mult=3.0, max_bars=30,
                 body_frac=0.4, trend=0):
    """Break-and-run: enter on a close beyond the prior N-bar extreme, size the
    stop from the signal candle's body, aim at a multiple of that risk.

    Returns a Series: +1 long, -1 short, 0 flat.
    """
    n = len(df)
    c = df["close"]
    o = df["open"]
    h = df["high"].shift(1)      # prior bars only
    l = df["low"].shift(1)

    hi = _swing_high(df, lookback)
    lo = _swing_low(df, lookback)

    body = (c - o).abs()
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    big = body >= body_frac * rng        # a decisive body, not a doji

    long_sig = (c > hi) & big & (df["close"].shift(1) <= hi)
    short_sig = (c < lo) & big & (df["close"].shift(1) >= lo)

    if trend:   # optional trend filter, shifted so it cannot leak
        t = df["close"].rolling(trend).mean().shift(1)
        long_sig &= c > t
        short_sig &= c < t

    out = np.zeros(n)
    pos, entry_i, direction = 0, 0, 0
    stop, target = 0.0, 0.0

    for i in range(1, n):
        if pos == 0:
            if long_sig.iloc[i]:
                b = body.iloc[i]
                direction = 1
                entry_i = i
                stop = c.iloc[i] - sl_mult * b
                target = c.iloc[i] + target_mult * sl_mult * b
                pos = 1
            elif short_sig.iloc[i]:
                b = body.iloc[i]
                direction = -1
                entry_i = i
                stop = c.iloc[i] + sl_mult * b
                target = c.iloc[i] - target_mult * sl_mult * b
                pos = 1
        else:
            hi_b, lo_b = df["high"].iloc[i], df["low"].iloc[i]
            if direction > 0:
                if lo_b <= stop or hi_b >= target or i - entry_i >= max_bars:
                    pos = 0
            else:
                if hi_b >= stop or lo_b <= target or i - entry_i >= max_bars:
                    pos = 0
        # signal is emitted for the NEXT bar's entry (engine fills at next open)
        out[i] = direction if pos else 0
    return pd.Series(out, index=df.index)


def sweep_candle(df, lookback=10, confirm=1, trend=0):
    """Liquidity sweep: price takes out a recent extreme but closes back inside
    it -- a failed breakout, which is the reversal side of the same idea."""
    n = len(df)
    hi = _swing_high(df, lookback)
    lo = _swing_low(df, lookback)
    c = df["close"]
    swept_high = (df["high"] > hi) & (c < hi)
    swept_low = (df["low"] < lo) & (c > lo)
    if confirm:
        swept_high &= c.shift(1) < hi.shift(1)
        swept_low &= c.shift(1) > lo.shift(1)
    if trend:
        t = df["close"].rolling(trend).mean().shift(1)
        swept_low &= c < t
        swept_high &= c > t
    out = np.zeros(n)
    for i in range(1, n):
        if swept_low.iloc[i]:
            out[i] = 1
        elif swept_high.iloc[i]:
            out[i] = -1
    return pd.Series(out, index=df.index)
