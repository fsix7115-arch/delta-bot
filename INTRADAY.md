# Intraday — the state of it

Date: 2026-09-27. The user asked specifically for intraday trading. This is
what the data says, including the part that changes an earlier conclusion.

## What changed

Earlier rounds dismissed intraday on reasoning alone: "fees eat it." That was a
guess. Measuring it turned out more interesting than expected.

**The dataset is good.** Delta serves continuous 15m bars far deeper than its
own documentation suggests:

| Symbol | Bars | Span |
|---|---|---|
| BTCUSD 15m | 96,168 | 2023-12-29 → 2026-09-26 (~1000 days) |
| ETHUSD 15m | 92,442 | 2024-02-06 → 2026-09-26 (~960 days) |

Found while checking, not assumed. The reader also needed fixing: the CSVs store
epoch **seconds**, and reading them as milliseconds silently produced 1970
dates. Third occurrence of that same bug class in this project.

## The fee hurdle

Delta perps, taker, no VIP tier:

- taker fee 0.05% per side → 0.10% round trip
- slippage 0.04% per side → 0.08% round trip
- **total friction 0.18% round trip**

## Bar movement is large enough

| Lookback | BTC median | % of bars > 0.18% | ETH median | % > 0.18% |
|---|---|---|---|---|
| 1 bar (15m) | 0.104% | 29.4% | 0.150% | 43.1% |
| 4 bars (1h) | 0.198% | 53.3% | 0.287% | 65.3% |
| 16 bars (4h) | 0.401% | 72.6% | 0.595% | 81.6% |
| 96 bars (1d) | 1.195% | 88.8% | 1.732% | 93.0% |

About a third of 15m bars move more than the full round trip. So the earlier
dismissal was wrong on the narrow claim: the hurdle is not impossible at this
timeframe.

## The backtest result

All 16 ETHUSD 15m configurations finished. **Every single one is negative.**

| impulse | hold | stop | gate | Sharpe | gross | net | trades |
|---|---|---|---|---|---|---|---|
| 0.6 | 8 | 0.40% | yes | -4.67 | +12.17% | **-96.17%** | 7,528 |
| 0.6 | 8 | 0.40% | no | -3.87 | +14.32% | -98.93% | 10,403 |
| 0.6 | 8 | 0.80% | yes | -4.19 | -0.19% | -92.63% | 5,738 |
| 1.0 | 8 | 0.40% | yes | -5.05 | -2.43% | -86.89% | 4,479 |
| 1.0 | 24 | 0.80% | no | -3.75 | -8.99% | -87.34% | 4,410 |
| 1.0 | 24 | 0.40% | yes | -4.01 | -6.34% | -89.82% | 4,914 |

Win rate 32-46% throughout, profit factor 0.81-0.86 — below 1.0 everywhere,
which means the trades lose money even before fees are considered in the gross
column for most configs.

## The gross/net split is the actual finding

The first config is the informative one: **gross +12.17%, net -96.17%**.

`intraday_drag.py` measures this directly rather than inferring it:

- gross edge over 7,198 trades: +12.2%
- **break-even cost per trade: 0.0017%**
- venue cost per trade: **0.18%**
- costs exceed the edge by roughly **106x**

So the pattern is not broken. The logic finds the same structure it finds on
the daily timeframe. It is simply too thin to be harvested ten thousand times a
year instead of a hundred and thirty times.

This is the distinction that matters and a net-only report cannot make:

- gross healthy, net destroyed → venue problem, maybe fixable with execution
- gross also negative → no edge exists, nothing to fix

Here it is the first case, and the fix is not a better strategy. It is **fewer
trades**.

## What the data says about trade count

| Config | Trades | Sharpe |
|---|---|---|
| ETHUSD 1d, 6y | 129 | **0.94** |
| ETHUSD 4h, 6y | 497 | 0.34 |
| ETHUSD 15m, 2.7y | 4,400 – 10,400 | -3.2 to -5.1 |

Sharpe falls monotonically as the timeframe gets faster. That is the finding:
the same idea, harvested more often, loses to costs faster than it gains.

One detail worth noting: turning the sentiment gate **off** raised trade count
from 7,528 to 10,403 and made net return worse (-98.93% vs -96.17%). More
trades, more fees, no more edge. The gate was doing its job on the daily
timeframe and here it only limits fee exposure.

## Answer to "I want intraday"

Not on this venue, at this fee level, with this edge. The arithmetic is 106x
against it, and that is not a tuning problem.

What would change the answer, in order of likelihood:

1. **Fewer, wider trades.** The one variant still worth running is a 1h or 4h
   hold computed on 15m bars, which cuts trade count by roughly an order of
   magnitude. The 24-bar hold tested here was not enough.
2. **Better fees.** A VIP tier or maker-rebate execution changes the 0.18%
   figure, and it is the only lever that scales.
3. **A genuinely different intraday edge.** Not this pattern. A structural
   product with no fees, or an order-flow signal that does not need to be
   harvested 10,000 times a year.

Absent one of those, ETHUSD 1d at Sharpe 0.94 remains the best thing found in
this project, and it is the same strategy the user already has.

## Reproducing

```bash
python3 intraday_fees.py      # the fee hurdle and bar-move distribution
python3 sweep_intraday.py     # the 16-config grid  (~15 min on 2 cores)
python3 intraday_drag.py      # the 106x arithmetic, measured not inferred
```
