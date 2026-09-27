# Research log — funding carry and the direction question

Date: 2026-09-27

## The request

"I want to make money whether the market goes up or down. A single trade should
be able to profit. Just tell me buy or sell."

This is worth taking seriously, because the delta-neutral carry trade is
genuinely designed for exactly that: it collects funding regardless of
direction. So it was tested properly rather than dismissed.

## Result: real, but too small to trade retail

Six years of real funding data, 6574 settlements per asset, 2020-09 to 2026-09.

| | BTCUSD | ETHUSD |
|---|---|---|
| Days with positive funding | 88.3% | 86.8% |
| Mean funding per day | +3.04 bp | +3.36 bp |
| Annualised, perp leg only | +11.1% | +12.3% |
| Median 30-day hold, gross | +0.53% | +0.50% |

The long-run bias is real. Funding is positive on roughly 7 days in 8, which is
the whole reason the trade exists.

Costs decide it. A round trip costs 0.10%, and fees are paid **once** while
funding accrues every 8 hours, so the cost amortises with the hold:

| Hold | BTC p5 net | ETH p5 net |
|---|---|---|
| 7d | -0.13% | -0.16% |
| 30d | -0.15% | -0.22% |
| 90d | +0.32% | -0.52% |
| 180d | +0.83% | -0.72% |
| 365d | +3.42% | +1.65% |

**p5 is the worst 1-in-20 window.** BTC needs a 60-day hold before the unlucky
case clears its own fees. ETH needs a full year. The median return over that
year is about 7%, on capital locked up for twelve months.

## Why this is not the answer

Three things, in order of how much they matter:

1. **These are perp-leg-only figures.** A genuine delta-neutral book is short
   perp + long spot. The spot leg pays its own round-trip fee, which roughly
   doubles the cost. Every number above should be cut about in half to become a
   real trade. Delta serves no public spot candles, so this could not be
   simulated honestly and was not simulated at all.

2. **A short-perp-only version is not direction-neutral.** It profits when
   price falls. Anyone running it as shown is making a directional bet and
   calling it carry. The "88% of days positive" figure is a statement about
   funding, not about price.

3. **It needs capital to sit still for months.** The entire edge is a fraction
   of a percent per month. At INR 35 (~$0.41) there is no position to hold, and
   even at INR 50,000 the absolute numbers would be a few hundred rupees a
   month, for a year of locked capital.

This is why exchanges market "passive income from your idle funds" rather than
telling you to run the trade yourself. The yield is real and it is small.

## Two bugs found while producing these numbers

Worth recording, because both produced spectacular results first:

1. **Timestamp unit.** The funding CSVs store epoch **seconds**. Parsing with
   `unit="ms"` gave 1970 dates, which collapsed the daily grouping and printed
   "+8104% annualised". `load_funding` now detects the unit.
2. **Column name.** The rate column is `rate`, not `funding_rate`. The loader
   now probes a list of candidate names.

The 8104% number appeared in output before it was caught. A headline that
extreme is a bug until proven otherwise.

## What this changes about the plan

Nothing about the primary strategy. The order-block plus sentiment-gate result
(Sharpe 0.94 on six years, ETHUSD 1d) remains the best thing found, and it is
direction-aware by design: it takes long or short depending on what the setup
shows. The user's framing of "I just want to know buy or sell" is compatible
with that, and the strategy already answers that question on every bar.

The funding carry is documented here so it does not get re-investigated. It is
not deployable at any realistic account size.
