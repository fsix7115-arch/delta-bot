# Shadow mode — what it is and what it is not

## The short version

Shadow mode runs the winning strategy on live Delta candles and logs what it
would have done. It places no orders and cannot, because the account holds
INR 35.01 (~$0.41) against a ~$10 minimum perp order.

What it is for: finding out whether a strategy that looked good on six years of
backtest behaves the same way on prices nobody has seen yet.

## The files

| File | Role |
|---|---|
| `shadow.py` | Fetches live candles, prints the current signal, appends to the log |
| `shadow_score.py` | Replays the logged signals forward and scores them |

Run both:

```bash
python3 shadow.py        # what is the signal right now
python3 shadow_score.py  # were the logged signals any good
```

A cron job (`81116a955e5e`) runs both every 4 hours and posts the result here.

## Why scoring is separate

A signal log on its own proves nothing. A system that is always long produces a
signal every single bar and makes no money. The only question worth asking is
whether following the log would have beaten not following it.

`shadow_score.py` replays each logged signal forward against the actual candles
using the same 2% stop and 8-bar hold as the backtest, then reports the same
shape of number. It also runs an **always-long baseline** with identical exit
rules, because "did better than doing nothing" is a much lower bar than "is
good" and it is worth knowing which one was cleared.

No lookahead: a signal logged at bar T is applied from bar T+1's open, matching
`engine.run`.

## Current state

3 log entries, 1 completed trade, +1.08%. **That is not a result.** Six entries
a day means 30 entries takes five days, and 30 entries is still thin. Nothing
should be concluded before then.

The backtest number for the same strategy is Sharpe 0.94 over six years on
ETHUSD 1d. Shadow mode runs ETHUSD 4h, which scored lower (0.34) on the same
six-year test — so the 4h shadow log is running the weaker of the two configs.
That is a deliberate choice: 4h gives six checks a day instead of one, which
accumulates evidence faster, and the score is reported honestly either way.

## What would change the verdict

- Shadow results diverging sharply from backtest, in either direction
- A drawdown materially worse than the backtest's -14.9%
- Signal frequency collapsing or doubling

Any of those and the strategy goes back to the drawing board regardless of what
the backtest says.
