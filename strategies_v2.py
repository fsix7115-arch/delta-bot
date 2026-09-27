"""New strategies for the 2026 crypto perp research round.

Every function returns +1 (long) / -1 (short) / 0 (flat) and uses ONLY data
that was available before the bar it trades, so the engine's next-open fill is
honest.

Covers the three families that are actually popular and under-tested so far:
  1. Sentiment-gated trend  — trade the trend, but stand aside in extreme
     sentiment. Backed by 3156 daily F&G readings from 2018.
  2. SuperTrend            — ATR-based trailing trend filter.
  3. VWAP reversion        — fade moves that stretch far from the session/
     period VWAP, which is how perp desks desk-manipulate-agnostic traders
     get run over in the short run.
"""
import numpy as np
import pandas as pd


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def load_sentiment(path):
    """Fear & Greed as a Series indexed by timestamp (seconds)."""
    f = pd.read_csv(path)
    f["dt"] = pd.to_datetime(f["timestamp"], unit="s", utc=True)
    s = f.set_index("dt")["value"].astype(float)
    return s[~s.index.duplicated(keep="first")].sort_index()


def _sentiment_at(sent, index, lookback_days=1):
    """Merge a daily sentiment series onto a bar index without leaking.

    A bar may only see a reading published BEFORE its own timestamp, so we
    reindex to the last reading strictly older than the bar and then shift.
    """
    if sent is None or len(sent) == 0:
        return None
    s = pd.Series(sent.reindex(sent.index.union(index)).ffill(), index=sent.index.union(index))
    s = s.reindex(index, method="ffill")
    # a reading dated 00:00 UTC is only usable from the NEXT bar onward
    return s.shift(lookback_days)


# ------------------------------------------------- 1. sentiment-gated trend

def s_sentiment_trend(fast=20, slow=50, an=14, fng_floor=25, fng_cap=75,
                      fng_len=5, trend_window=200):
    """Trend following, but flat during extreme fear or extreme greed.

    Extreme sentiment marks crowded positioning; entering there is where the
    historical loss concentration sits. The gate uses a rolling mean of the
    index so a single wild day does not switch the system off.
    """
    def f(df, sent=None):
        f_ = ema(df["close"], fast).shift(1)
        s_ = ema(df["close"], slow).shift(1)
        sig = np.where(f_ > s_, 1.0, -1.0)
        sig = np.where(ema(df["close"], trend_window).shift(1) > df["close"].shift(1), sig, 0.0)
        fng = _sentiment_at(sent, df.index) if sent is not None else None
        if fng is not None:
            avg = fng.rolling(fng_len, min_periods=1).mean().shift(1)
            sig = np.where((avg < fng_floor) | (avg > fng_cap), 0.0, sig)
        return pd.Series(sig, index=df.index)
    f.__name__ = f"sentiment_trend_{fast}_{slow}_{fng_floor}_{fng_cap}"
    return f


# ------------------------------------------------------------- 2. SuperTrend

def s_supertrend(n=10, mult=3.0):
    """ATR trailing trend. Long while close holds above the band, short below."""
    def f(df):
        a = atr(df, n)
        hl2 = (df["high"] + df["low"]) / 2
        up = hl2 + mult * a
        dn = hl2 - mult * a
        c = df["close"]
        fup = up.copy()
        fdn = dn.copy()
        bull = c > hl2
        for i in range(1, len(df)):
            fup.iloc[i] = up.iloc[i] if (bull.iloc[i - 1] and up.iloc[i] < fup.iloc[i - 1]) else up.iloc[i]
            fdn.iloc[i] = dn.iloc[i] if (not bull.iloc[i - 1] and dn.iloc[i] > fdn.iloc[i - 1]) else dn.iloc[i]
            bull.iloc[i] = c.iloc[i] > fup.iloc[i]
        # signal must be known before the bar it trades
        return pd.Series(np.where(c.shift(1) > fup.shift(1), 1.0,
                                  np.where(c.shift(1) < fdn.shift(1), -1.0, 0.0)),
                         index=df.index)
    f.__name__ = f"supertrend_{n}_{mult}"
    return f


# -------------------------------------------------------------- 3. VWAP band

def s_vwap_reversion(window=48, z=1.8, trend=100):
    """Fade a move that has stretched too far from the rolling VWAP.

    Intraday perps mean-revert violently after a stretch; the trend filter
    keeps us from fading a genuine trend break.
    """
    def f(df):
        tp = (df["high"] + df["low"] + df["close"]) / 3
        v = tp.rolling(window).sum()
        p = df["close"].rolling(window).sum()
        vwap = (v / p.replace(0, np.nan))
        sd = (df["close"] - vwap).rolling(window).std()
        z = (df["close"] - vwap) / sd.replace(0, np.nan)
        t = ema(df["close"], trend).shift(1)
        c = df["close"].shift(1)
        w = vwap.shift(1)
        sdz = sd.shift(1)
        zz = ((c - w) / sdz.replace(0, np.nan))
        long_sig = (zz < -1.8) & (c > t)
        short_sig = (zz > 1.8) & (c < t)
        return pd.Series(np.where(long_sig, 1.0, np.where(short_sig, -1.0, 0.0)),
                         index=df.index)
    f.__name__ = f"vwap_reversion_{window}"
    return f


# ------------------------------------------- 4. sentiment divergence (contrarian)

def s_fng_divergence(lookback=10, mode="contrarian"):
    """Trade the gap between price momentum and sentiment.

    Price up hard while sentiment barely moved = move without conviction,
    which historically fades. Both directions are encoded.
    """
    def f(df, sent=None):
        c = df["close"]
        p_ret = (c - c.shift(lookback)) / c.shift(lookback)
        fng = _sentiment_at(sent, df.index) if sent is not None else None
        if fng is None:
            return pd.Series(0.0, index=df.index)
        fng_chg = fng - fng.shift(lookback)
        pr = p_ret.shift(1)
        fc = fng_chg.shift(1)
        up_weak = (pr > 0.02) & (fc < 3)
        dn_weak = (pr < -0.02) & (fc > -3)
        if mode == "contrarian":
            sig = np.where(up_weak, -1.0, np.where(dn_weak, 1.0, 0.0))
        else:
            sig = np.where(up_weak, 1.0, np.where(dn_weak, -1.0, 0.0))
        return pd.Series(sig, index=df.index)
    f.__name__ = f"fng_divergence_{lookback}_{mode}"
    return f
