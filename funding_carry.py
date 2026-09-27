"""Delta-neutral funding carry: profit from funding, not from direction.

The request was "I want to make money whether the market goes up or down." That
is exactly what a market-neutral carry trade does, and it is the only family
here that does not require predicting direction at all.

How it works on a perpetual futures venue:

  Funding is a periodic payment between long and short holders, usually every
  8 hours. When longs are crowded and pay, a SHORT receives funding. So:

      short perp  ->  receives funding when the rate is positive
      long  spot  ->  cancels the price risk of the short

  Price moves up   -> the short loses roughly what the long gains
  Price moves down -> the short gains roughly what the long loses
  Funding positive -> the short is paid, every 8 hours

  Direction cancels. What is left is the carry, plus whatever basis and fee
  drag sits in between.

This script does NOT simulate the spot leg, because Delta's public API does not
serve spot candles and I will not invent them. It therefore reports funding
income ALONE, gross, and then subtracts realistic round-trip costs. If the
number survives that, the strategy is real. If it does not, no amount of
sophistication will save it.

The honest caveat, stated up front: a genuinely delta-neutral book needs the
spot leg, and that is where the basis risk and the extra fees live. A
single-venue version (short perp only) is NOT delta-neutral -- it profits when
price falls, which is a directional bet wearing a costume.
"""
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, "data", "extended")

# Delta's taker fee is ~0.05% per side on perps. A short entry plus exit is
# two legs, and a delta-neutral book pays that twice (perp + spot).
TAKER_FEE = 0.0005
SETTLE_HOURS = 8


def load_funding(symbol):
    """Read the funding history CSV.

    The stored timestamps are SECONDS, not milliseconds -- converting with
    unit="ms" silently produces 1970 dates and then a nonsense "8000%
    annualised" number, because the daily grouping collapses to nothing and
    the mean looks enormous. Detect the unit rather than assuming it.
    """
    p = os.path.join(EXT, f"{symbol}_funding.csv")
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p)
    tcol = "time" if "time" in df.columns else df.columns[0]
    raw = pd.to_numeric(df[tcol], errors="coerce")
    if raw.dropna().empty:
        return None
    # Anything past ~2286-11-20 in seconds is beyond datetime range, and any
    # plausible epoch-seconds value is ~1.8e9 vs ~1.8e12 for ms.
    unit = "s" if raw.max() < 1e11 else "ms"
    idx = pd.to_datetime(raw, unit=unit, utc=True, errors="coerce")
    df = df.assign(**{tcol: idx}).dropna(subset=[tcol])
    df = df.set_index(tcol).sort_index()

    for cand in ("funding_rate", "rate", "fundingRate"):
        if cand in df.columns:
            rcol = cand
            break
    else:
        rcol = df.columns[-1]
    s = df[rcol].astype(float)
    return s[~s.index.duplicated(keep="last")]


def analyse(symbol, threshold=0.0, hold_days=30):
    r = load_funding(symbol)
    if r is None:
        return None
    # Funding is quoted as a fraction per 8h settlement (0.0001 = 0.01%).
    daily = r.groupby(r.index.floor("D")).sum()
    annual = daily * 365

    pos = daily[daily > threshold]
    neg = daily[daily <= threshold]
    win = pos.mean() * 365 if len(pos) else 0.0
    loss = neg.mean() * 365 if len(neg) else 0.0

    # Fraction of days funding was positive at all. This is the whole game: the
    # long-run bias, not any skill at picking settlement times.
    frac_pos = (daily > 0).mean()
    hold = hold_days
    mean_daily = daily.mean()
    ret = daily.rolling(hold).sum()

    out = {
        "symbol": symbol,
        "rows": int(len(r)),
        "from": str(r.index[0])[:10],
        "to": str(r.index[-1])[:10],
        "mean_daily_bp": mean_daily * 1e4,
        "median_daily_bp": daily.median() * 1e4,
        "frac_days_positive": frac_pos * 100,
        "annualised_if_short_always": mean_daily * 365 * 100,
        "annualised_when_pos": win,
        "annualised_when_neg": loss,
        "worst_day_bp": daily.min() * 1e4,
        "best_day_bp": daily.max() * 1e4,
        "days": len(daily),
    }
    if len(ret.dropna()) > 20:
        out["p5_30d_gross"] = np.nanpercentile(ret.dropna(), 5) * 100
        out["median_30d_gross"] = np.nanmedian(ret.dropna()) * 100
        # Cost of a round trip on the perp leg only.
        out["roundtrip_cost_pct"] = TAKER_FEE * 2 * 100
        out["p5_30d_net"] = out["p5_30d_gross"] - out["roundtrip_cost_pct"]
    return out


def main():
    print("=" * 74)
    print("  FUNDING CARRY  —  is there a real long-run bias, and can it beat costs?")
    print("=" * 74)
    rows = []
    for sym in ("BTCUSD", "ETHUSD"):
        a = analyse(sym)
        if a:
            rows.append(a)

    for a in rows:
        print(f"\n--- {a['symbol']}  ({a['rows']} settlements, "
              f"{a['from']} to {a['to']}) ---")
        print(f"  days with positive funding : {a['frac_days_positive']:5.1f}%")
        print(f"  mean funding per day       : {a['mean_daily_bp']:+7.2f} bp "
              f"({a['mean_daily_bp']/100:+.4f}%)")
        print(f"  median funding per day     : {a['median_daily_bp']:+7.2f} bp")
        print(f"  worst / best day           : {a['worst_day_bp']:+7.2f} / "
              f"{a['best_day_bp']:+7.2f} bp")
        print(f"  ANNUALISED, short only     : "
              f"{a['annualised_if_short_always']:+7.1f}%")
        if "p5_30d_gross" in a:
            print(f"  30-day holding, gross      : p5 {a['p5_30d_gross']:+6.2f}%  "
                  f"median {a['median_30d_gross']:+6.2f}%")
            print(f"  30-day holding, NET of fees: p5 {a['p5_30d_net']:+6.2f}%  "
                  f"(cost {a['roundtrip_cost_pct']:.2f}%)")
            verdict = "survives costs" if a["p5_30d_net"] > 0 else "EATEN BY COSTS"
            print(f"  -> {verdict}")

    print("\n" + "=" * 74)
    print("""
READ THIS BEFORE TRUSTING ANYTHING ABOVE

1. A short-perp-only version is NOT delta-neutral. It profits when price
   falls. That is a directional bet. The number above is an UPPER BOUND that
   assumes you are short and the price happens to cooperate.

2. A real delta-neutral book is: short perp + long spot, same size. Price risk
   cancels and you keep the funding. Delta serves no spot candles publicly, so
   this script does not simulate it. Adding a spot leg adds its own fees and
   its own basis risk.

3. Funding rates are 8-hourly, quoted per settlement. Annualising the mean
   assumes it persists, which is an assumption, not a fact.

4. The real question for a retail account is not "does this work on average"
   but "does it work after funding flips negative for two weeks while you are
   short." The 30-day p5 column is the closest thing here to that answer.
""")


if __name__ == "__main__":
    main()
