"""Strategy signal library. Each function returns +1 (long) / -1 (short) / 0 (flat).

Every signal is a pure function of PAST data only: indicators use `.shift(1)`
where a value would otherwise leak the current bar into the decision.
"""
import numpy as np
import pandas as pd


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df, n=14):
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def macd(s, fast=12, slow=26, sig=9):
    m = ema(s, fast) - ema(s, slow)
    return m, ema(m, sig), m - ema(m, sig)


def adx(df, n=14):
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    mdi = 100 * pd.Series(minus, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    dx = (100 * (pdi - mdi).abs() / (pdi + mdi)).fillna(0)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, mdi


# ---------------------------------------------------------------- strategies

def s_ema_cross(fast, slow):
    def f(df):
        f_ = ema(df["close"], fast).shift(1)
        s_ = ema(df["close"], slow).shift(1)
        return pd.Series(np.sign(f_ - s_), index=df.index)
    f.__name__ = f"ema_cross_{fast}_{slow}"
    return f


def s_trend_rsi(fast, slow, rlen=14, lo=40, hi=60):
    """Trend-following gated by RSI: only stay long when RSI is not exhausted."""
    def f(df):
        f_ = ema(df["close"], fast).shift(1)
        s_ = ema(df["close"], slow).shift(1)
        r = rsi(df["close"], rlen).shift(1)
        sig = np.where(f_ > s_, 1.0, -1.0)
        sig = np.where(r > hi, 0.0, sig)
        sig = np.where(r < lo, 0.0, sig)
        return pd.Series(sig, index=df.index)
    f.__name__ = f"trend_rsi_{fast}_{slow}_{lo}_{hi}"
    return f


def s_breakout(n):
    def f(df):
        hi = df["high"].rolling(n).max().shift(1)
        lo = df["low"].rolling(n).min().shift(1)
        c = df["close"].shift(1)
        return pd.Series(np.where(c > hi, 1.0, np.where(c < lo, -1.0, 0.0)),
                         index=df.index)
    f.__name__ = f"breakout_{n}"
    return f


def s_macd(fast=12, slow=26, sig=9):
    def f(df):
        _, _, h = macd(df["close"].shift(1), fast, slow, sig)
        return pd.Series(np.sign(h), index=df.index)
    f.__name__ = f"macd_{fast}_{slow}_{sig}"
    return f


def s_donchian_trend(a=20, b=100):
    def f(df):
        hi = df["high"].rolling(a).max().shift(1)
        lo = df["low"].rolling(a).min().shift(1)
        mid = (df["close"].rolling(b).mean()).shift(1)
        c = df["close"].shift(1)
        return pd.Series(np.where(c > hi, 1.0,
                         np.where(c < lo, -1.0,
                         np.where(c > mid, 1.0, np.where(c < mid, -1.0, 0.0)))),
                         index=df.index)
    f.__name__ = f"donchian_trend_{a}_{b}"
    return f


def s_atr_breakout(n=20, k=1.0, trend=50):
    """Volatility expansion: close beyond prior N-bar extreme, aligned to trend."""
    def f(df):
        hi = df["high"].rolling(n).max().shift(1)
        lo = df["low"].rolling(n).min().shift(1)
        c = df["close"].shift(1)
        t = ema(df["close"], trend).shift(1)
        long = (c > hi) & (c > t)
        short = (c < lo) & (c < t)
        return pd.Series(np.where(long, 1.0, np.where(short, -1.0, 0.0)),
                         index=df.index)
    f.__name__ = f"atr_breakout_{n}_{trend}"
    return f


def s_mean_revert(n=50, z=1.5):
    """Fade extremes: short > +z sigma, long < -z sigma, flat in between."""
    def f(df):
        ma = df["close"].rolling(n).mean().shift(1)
        sd = df["close"].rolling(n).std().shift(1)
        c = df["close"].shift(1)
        zs = (c - ma) / sd.replace(0, np.nan)
        return pd.Series(np.where(zs > z, -1.0, np.where(zs < -z, 1.0, 0.0)),
                         index=df.index)
    f.__name__ = f"mean_revert_{n}_{z}"
    return f


def s_rsi_revert(n=50, rlen=14, lo=30, hi=70):
    def f(df):
        r = rsi(df["close"], rlen).shift(1)
        c = df["close"].rolling(n).mean().shift(1)
        px = df["close"].shift(1)
        return pd.Series(np.where((r < lo) & (px < c), 1.0,
                         np.where((r > hi) & (px > c), -1.0, 0.0)), index=df.index)
    f.__name__ = f"rsi_revert_{rlen}_{lo}_{hi}"
    return f


def s_adx_trend(fast=20, slow=50, an=14, thresh=20):
    def f(df):
        a, _, _ = adx(df, an)
        f_ = ema(df["close"], fast).shift(1)
        s_ = ema(df["close"], slow).shift(1)
        sig = np.where(f_ > s_, 1.0, -1.0)
        return pd.Series(np.where(a.shift(1) > thresh, sig, 0.0), index=df.index)
    f.__name__ = f"adx_trend_{fast}_{slow}"
    return f


def s_vol_regime_breakout(n=20, trend=50, lookback=100):
    """Breakout, but only when realised vol is above its own median-ish level."""
    def f(df):
        ret = df["close"].pct_change()
        vol = ret.rolling(lookback).std().shift(1)
        vol_ma = vol.rolling(lookback).mean().shift(1)
        hi = df["high"].rolling(n).max().shift(1)
        lo = df["low"].rolling(n).min().shift(1)
        c = df["close"].shift(1)
        t = ema(df["close"], trend).shift(1)
        hot = vol > vol_ma
        return pd.Series(np.where((c > hi) & (c > t) & hot, 1.0,
                         np.where((c < lo) & (c < t) & hot, -1.0, 0.0)),
                         index=df.index)
    f.__name__ = f"vol_regime_breakout_{n}_{trend}"
    return f
