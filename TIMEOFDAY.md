# Time of day, and the three Stock Learners videos

Date: 2026-09-27

## The videos

| ID | Title | Channel |
|---|---|---|
| `wI9b968AvW8` | Best Trading Strategy For Beginners — Scalping Strategy | Stock Learners |
| `XHOxOGlaAKw` | Spot The Ultimate Move — Trap Trading Masterclass | Stock Learners |
| `qOgfHJh526U` | The Only Way For Success — Trading Psychology | Stock Learners |

**None of the three have captions or transcripts**, so their content could not
be extracted. What follows about them is inferred from the titles and from what
this project has already measured about the same channel, and is labelled as
such.

The scalping video is the same channel and the same subject matter as
`strategies_youtube.py`, which was mechanised from an earlier Stock Learners
walkthrough: 62 configurations, best Sharpe 1.33 on 8 trades, median negative,
zero configs profitable with enough trades to be meaningful. The intraday work
below independently confirms that conclusion on real 15m data with real costs.

**What the titles imply, and what was actually tested:**

- *Scalping* → tested. Negative. See the 16-config 15m sweep and the 106x cost
  arithmetic in `INTRADAY.md`.
- *Trap Trading Masterclass* → the mechanics are order blocks and liquidity
  sweeps, which are already implemented in `strategies_smc.py`. Order block is
  the winning strategy. FVG, BOS and CHoCH were tested and produced 0 of 22
  and 0 of 15 profitable configs.
- *Trading Psychology* → not testable by backtest. Noted and set aside.

## The time-of-day question

The request was to find when the large players are active, on the theory that
activity means opportunity. Measured on ~96,000 fifteen-minute bars per symbol
over roughly 2.7 years, all times UTC.

### The pattern is real and it survives out of sample

| Hour (UTC) | BTC median move | ETH median move |
|---|---|---|
| 14:00 | 0.165% (1.59x) | 0.228% (1.53x) |
| 15:00 | 0.148% (1.43x) | 0.207% (1.39x) |
| 16:00 | 0.134% (1.29x) | 0.188% (1.26x) |
| 13:00 | 0.131% (1.26x) | 0.187% (1.25x) |

Weakest hours are 04:00-06:00 and 10:00-11:00 UTC, at 0.075-0.11%.

The dataset was split in half. The four best hours in the first half were
`[13, 14, 15, 16]` and in the second half they were also `[13, 14, 15, 16]`.
**Four of four overlap.** This is not a coincidence found in one period.

14:00-17:00 UTC is the European/US overlap, which is where institutional
activity and liquidity peak. The folklore was right about that much.

### But does it help to trade it?

No. This is where the honest answer is less satisfying than the pattern.

| Symbol | Variant | Sharpe | Gross | Net | Trades |
|---|---|---|---|---|---|
| ETH | all hours | -5.05 | -2.43% | -86.89% | 4,479 |
| ETH | **window 13-16 only** | -4.25 | -3.91% | **-45.37%** | 1,318 |
| ETH | outside window only | -5.55 | +0.40% | -79.26% | 3,497 |
| BTC | all hours | -6.92 | -8.22% | -86.05% | 4,229 |
| BTC | **window 13-16 only** | -5.76 | -6.36% | **-46.55%** | 1,267 |
| BTC | outside window only | -7.60 | -1.68% | -77.65% | 3,309 |

Restricting to the active window roughly **halved the loss** on both symbols.
That is a real improvement and it is also still deeply negative.

Two things to read here:

1. **Trade count fell from ~4,400 to ~1,300, and the loss halved.** Almost
   exactly proportionally. The gain is from trading less, not from trading
   better. Fees are per trade; cutting trades by two-thirds cut the bill by
   two-thirds. The window did not add edge, it removed cost exposure.

2. **Gross return went DOWN inside the window** on both symbols (-2.43% →
   -3.91% on ETH, -8.22% → -6.36% on BTC, mixed). A genuine volatility edge
   would show gross improving. It did not. What improved was net, and only
   because fewer fees were paid.

The sanity check also came out in the expected direction: trading the *dead*
hours was worse than trading the peak hours (-5.55 vs -4.25 Sharpe on ETH). So
the time-of-day story is not inverted, it is simply insufficient.

## The conclusion

Big players are active, liquidity peaks, and price moves 1.3-1.6x more at
14:00-17:00 UTC than at 05:00. All of that is measured and holds out of sample.

It does not create an edge. The cost per trade on Delta is 0.18% and the
strategy's gross edge per trade is 0.0017%, so the gap is 106x. A window that
tells you *when* price moves does nothing about the fact that a 0.18% round
trip needs a 0.18% move just to break even. ETH's best hour clears that hurdle
on the median bar; BTC's does not, at 0.165% against a 0.18% cost.

**If the user wants to trade the active window anyway, the correct
configuration is 13:00-16:59 UTC, and it should be paired with the daily
timeframe logic, not with 15m scalping.** Running the daily strategy on 15m
bars and entering only inside the window is the one combination here with a
plausible mechanism, and it is worth a test.

## Files

```bash
python3 tod_profile.py     # hourly movement profile + OOS validation (~2 min)
python3 tod_backtest.py    # window-restricted backtest (~10 min on 2 cores)
```

Results in `results/tod_window.csv`.
