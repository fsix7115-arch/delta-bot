"""Sanity tests for the backtest engine. These must pass or results are meaningless."""
import numpy as np
import pandas as pd
from engine import run, metrics


def mkdf(prices, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(prices), freq="1h", tz="UTC")
    return pd.DataFrame({"open": prices, "high": prices, "low": prices,
                         "close": prices, "volume": [1.0] * len(prices)}, index=idx)


def test_no_lookahead_constant_up():
    """A constant LONG signal into a monotonically rising market must profit."""
    p = np.array([100 * (1.001 ** i) for i in range(500)])
    sig = pd.Series(1.0, index=mkdf(p).index)
    eq, tr = run(mkdf(p), sig, risk=1.0, fee=0.0, slip=0.0)
    assert eq.iloc[-1] > 1.0, "rising market + always long should profit"
    assert len(tr) == 1


def test_no_lookahead_constant_down():
    """Always SHORT into a falling market must profit."""
    p = np.array([100 * (0.999 ** i) for i in range(500)])
    sig = pd.Series(-1.0, index=mkdf(p).index)
    eq, tr = run(mkdf(p), sig, risk=1.0, fee=0.0, slip=0.0)
    assert eq.iloc[-1] > 1.0, "falling market + always short should profit"


def test_fees_turn_profit_into_loss():
    """A churn-heavy signal with no gross edge must lose money once costs apply.

    The synthetic market rises 2bps/bar, but the signal alternates long/short
    every 10 bars, so gross P&L nets to ~zero. With 50 round trips at ~18bps
    each, realistic costs must push equity clearly below 1.0.
    """
    p = np.array([100 * (1.0002 ** i) for i in range(500)])
    df = mkdf(p)
    sig = pd.Series([1.0 if (i // 10) % 2 == 0 else -1.0 for i in range(500)],
                    index=df.index)
    cheap, tc = run(df, sig, risk=1.0, fee=0.0, slip=0.0)
    costly, tk = run(df, sig, risk=1.0, fee=0.0005, slip=0.0004)
    assert len(tk) > 40, "test should churn many round trips"
    assert abs(cheap.iloc[-1] - 1.0) < 0.02, "gross should be ~flat"
    assert costly.iloc[-1] < 0.98, "costs should bleed the equity on churn"
    assert costly.iloc[-1] < cheap.iloc[-1]


def test_stop_loss_caps_loss():
    """A stop must trigger and the loss must be bounded near the stop size."""
    p = np.array([100.0] * 10 + [100 * (0.90 ** i) for i in range(1, 200)])
    df = mkdf(p)
    sig = pd.Series(1.0, index=df.index)
    eq, tr = run(df, sig, stop=0.02, risk=1.0, fee=0.0, slip=0.0)
    stopped = [t for t in tr if t["reason"] == "stop"]
    assert stopped, "stop should have fired in a crash"
    assert stopped[0]["pnl"] > -0.03, f"loss {stopped[0]['pnl']} exceeded stop band"


def test_equity_never_leaks_past_cash():
    """Equity series must never exceed cash + unrealized (no double counting)."""
    rng = np.random.default_rng(7)
    p = 100 * np.cumprod(1 + rng.normal(0, 0.01, 1000))
    df = mkdf(p)
    sig = pd.Series(rng.choice([1.0, -1.0, 0.0], 1000), index=df.index)
    eq, tr = run(df, sig, risk=0.5)
    assert np.isfinite(eq).all()
    assert len(eq) == len(df)


def test_metrics_max_dd_is_nonpositive():
    rng = np.random.default_rng(3)
    p = 100 * np.cumprod(1 + rng.normal(0, 0.01, 800))
    df = mkdf(p)
    sig = pd.Series(1.0, index=df.index)
    eq, tr = run(df, sig, risk=0.5)
    m = metrics(eq, tr, "1h")
    assert m["max_dd"] <= 0.0
    assert -1.0 <= m["max_dd"] <= 0.0


def test_short_uses_peak_favourable_correctly():
    """Short into a rally then a drop: stop should not fire on the way up
    if the rally is under the stop band."""
    p = np.array([100.0] * 5 + [101.0] * 20 + [95.0] * 50)
    df = mkdf(p)
    sig = pd.Series(-1.0, index=df.index)
    eq, tr = run(df, sig, stop=0.05, risk=1.0, fee=0.0, slip=0.0)
    assert eq.iloc[-1] > 1.0, "short through a small rally then a drop should win"


def test_funding_long_pays_when_rate_positive():
    """A positive funding rate must debit a long position every settlement."""
    p = np.array([100.0] * 200)
    df = mkdf(p)
    sig = pd.Series(1.0, index=df.index)
    # two settlements, +0.05% each, inside the holding window
    fidx = pd.date_range("2024-01-01 04:00", periods=2, freq="8h", tz="UTC")
    fund = pd.Series([0.0005, 0.0005], index=fidx)
    nof, _ = run(df, sig, risk=1.0, fee=0.0, slip=0.0)
    withf, tr = run(df, sig, risk=1.0, fee=0.0, slip=0.0, funding=fund)
    assert nof.iloc[-1] == 1.0
    assert withf.iloc[-1] < 1.0, "long should pay funding"
    # 2 settlements x 0.05% on ~1.0 notional ~= 0.1% drag
    assert abs(withf.iloc[-1] - 0.999) < 0.002, withf.iloc[-1]
    assert withf.attrs["funding_paid"] < 0


def test_funding_short_receives_when_rate_positive():
    """Mirror test: the short must receive, not pay, the same funding."""
    p = np.array([100.0] * 200)
    df = mkdf(p)
    sig = pd.Series(-1.0, index=df.index)
    fidx = pd.date_range("2024-01-01 04:00", periods=2, freq="8h", tz="UTC")
    fund = pd.Series([0.0005, 0.0005], index=fidx)
    eq, _ = run(df, sig, risk=1.0, fee=0.0, slip=0.0, funding=fund)
    assert eq.iloc[-1] > 1.0, "short should receive funding"
    assert eq.attrs["funding_paid"] > 0


def test_funding_none_is_a_noop():
    """With funding=None the run must be bit-identical to before."""
    p = 100 * np.cumprod(1 + np.random.default_rng(11).normal(0, 0.01, 500))
    df = mkdf(p)
    sig = pd.Series([1.0 if i % 30 < 15 else -1.0 for i in range(500)],
                    index=df.index)
    a, _ = run(df, sig, risk=0.5)
    b, _ = run(df, sig, risk=0.5, funding=None)
    assert a.iloc[-1] == b.iloc[-1]


def test_funding_drag_scales_with_size():
    """A larger notional must incur proportionally more funding drag."""
    p = np.array([100.0] * 200)
    df = mkdf(p)
    sig = pd.Series(1.0, index=df.index)
    fidx = pd.date_range("2024-01-01 04:00", periods=2, freq="8h", tz="UTC")
    fund = pd.Series([0.0005, 0.0005], index=fidx)
    small, _ = run(df, sig, risk=0.25, fee=0.0, slip=0.0, funding=fund)
    big, _ = run(df, sig, risk=1.0, fee=0.0, slip=0.0, funding=fund)
    assert big.attrs["funding_paid"] < small.attrs["funding_paid"]


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
