"""Does the funding carry survive costs if you hold longer?

funding_carry.py showed funding is genuinely positive ~88% of days and worth
~11-12% annualised, but that a 30-day round trip gets eaten by fees. That
framing hides the actual mechanic: fees are paid ONCE per position, while
funding accrues every 8 hours. So the cost is amortised over the holding
period, and a longer hold has a fundamentally different cost structure.

The question this answers: is there a holding period where the carry is
positive at the 5th percentile, i.e. where even the unlucky windows clear their
own fees?

Not modelled, and it matters: the delta-neutral version needs a long spot leg,
which pays its own round-trip fee. The figures below are therefore the
PERP-ONLY upper bound, and a real delta-neutral book halves the margin again.
"""
import os

import numpy as np
import pandas as pd

from funding_carry import load_funding, TAKER_FEE

PERIODS = (7, 14, 30, 60, 90, 180, 365)


def main():
    print("=" * 78)
    print("  HOLDING PERIOD vs COST  —  perp leg only, gross and net")
    print("=" * 78)
    for sym in ("BTCUSD", "ETHUSD"):
        r = load_funding(sym)
        if r is None:
            continue
        daily = r.groupby(r.index.floor("D")).sum()
        print(f"\n--- {sym}  ({len(daily)} days, "
              f"{str(daily.index[0])[:10]} to {str(daily.index[-1])[:10]}) ---")
        print(f"{'hold':>5s} {'windows':>8s} {'p5 gross':>10s} {'p50':>8s} "
              f"{'cost':>7s} {'p5 NET':>9s} {'verdict':>14s}")
        for h in PERIODS:
            rolls = daily.rolling(h).sum().dropna()
            if len(rolls) < 30:
                continue
            p5 = np.nanpercentile(rolls, 5) * 100
            p50 = np.nanmedian(rolls) * 100
            cost = TAKER_FEE * 2 * 100
            net = p5 - cost
            verdict = "survives" if net > 0 else "loses at p5"
            print(f"{h:>4d}d {len(rolls):>8d} {p5:>+9.2f}% {p50:>+7.2f}% "
                  f"{cost:>6.2f}% {net:>+8.2f}% {verdict:>14s}")

    print("\n" + "=" * 78)
    print("""
HOW TO READ THIS

The p5 column is the important one. It is the worst 1-in-20 window. A strategy
only worth running has p5 NET of fees above zero, because that means even the
unlucky stretches paid for themselves.

If a longer hold clears p5 net, the strategy is real but slow: it needs capital
sitting still for months, and the return is a fraction of the headline annualised
figure. If no hold period clears it, the carry is real but too small to trade
retail -- which is the usual answer, and the reason the "free money" videos
show exchange-native yield products instead of asking you to run this yourself.
""")


if __name__ == "__main__":
    main()
