# delta-bot

Backtesting research for BTC/ETH perpetual futures on Delta Exchange India.

The headline number is easy to get wrong. This project is mostly about the
five bugs that produced fake results before producing real ones, so they are
documented below rather than hidden.

## What actually works

Order block entries (Smart Money Concepts) gated by crypto sentiment, on
**ETHUSD 1d**:

| Metric | Value |
|---|---|
| Sharpe | **0.94** (6y, out-of-sample) |
| Sharpe at 2x costs | 0.85 |
| CAGR | +18.5% |
| Max drawdown | -14.9% |
| Trades | 129 |
| Buy and hold, same window | +8.8% |

Quote 0.94, not 2.88. The sentiment-gated variant printed Sharpe 2.88 on two
years of data and fell to 0.94 once the 2020 crash and 2022 bear market were
included. The ungated order block did the same thing: 1.01 on 2y, 0.60 on 6y.

**ETH only.** On BTC, buy-and-hold wins by a wide margin (+101% vs +0.5% over
6y). The sentiment index is BTC-centric but did not predict BTC perps here.

## Strategy

An order block is tagged when a down-candle is followed by a 3-candle rally
larger than 1x ATR. When price returns into that candle's body, enter long.
Stop 2%, target 3x that, maximum hold 8 bars.

The sentiment gate suppresses entries when the 5-day mean Fear & Greed index
is outside 20-80, which removed enough of the worst trades to lift Sharpe from
0.60 to 0.94.

## The five bugs

Every one of these produced a spectacular, fake result. If a backtest here
ever prints a Sharpe above ~3, assume a bug until proven otherwise.

1. **P&L double-counted.** `qty` is already in units, so P&L is
   `qty * (price - entry)`. Dividing by `entry` again produced Sharpe values
   like -40.
2. **Funding double-counted.** The funding window must be bounded by
   `settled_t`, not `entry_t`, or every 8-hour settlement is re-charged on
   every bar. Gave a 5% drag instead of 0.1%.
3. **Zero-return bars filtered out of the volatility calculation.** A strategy
   sitting flat has low volatility; removing those bars shrinks the Sharpe
   denominator and inflates it without bound. Produced **Sharpe 680**.
4. **Lookahead leak in the order block detector.** The block was tagged at its
   own birth bar while reading the next three candles to confirm the impulse —
   a move that had not happened yet. 87% win rate, 1643% CAGR.
5. **Pattern signals never held.** A pattern signal is an entry event, not a
   per-bar state. Without `hold_bars` the engine opened and closed on the same
   bar and skipped the round-trip cost entirely.

## Getting started

```bash
pip install pandas numpy
python3 test_engine.py        # 11 tests, must pass before trusting anything
python3 test_lookahead.py     # guards the pattern detectors
python3 fetch_data.py         # Delta candles, ~2 years (no API key needed)
python3 fetch_extended.py     # 6 years of Binance candles + real funding rates
python3 fetch_sentiment.py    # Fear & Greed index, 2018 to now
python3 hybrid_6y.py          # reproduce the headline result
```

## Layout

| File | Purpose |
|---|---|
| `engine.py` | Backtest engine: next-bar fills, fees and slippage on both legs, real funding, degeneracy guard |
| `strategies_smc.py` | Order block, FVG, liquidity grab, BOS/CHoCH |
| `strategies_v2.py` | SuperTrend, VWAP reversion, sentiment-gated trend, F&G divergence |
| `strategies.py` | 20 classic signal generators |
| `hybrid.py`, `hybrid_6y.py` | Order block merged with sentiment gating |
| `validate_6y.py` | 6-year validation with cost stress |
| `vet_hybrid.py` | Guards against believing an implausibly good result |
| `monte_carlo.py` | Bootstrap of the trade sequence: P(loss), p5, worst drawdown |
| `shadow.py` | Live shadow mode, places no orders |
| `llm.py` | Free Gemini and Groq clients (retry logic for the shared free tier) |

## Data sources

- **Delta Exchange** serves about 2 years of candles. That is a hard limit, and
  it means the 2020 crash and 2022 bear market are not available from the venue
  we would actually trade on.
- **Binance** provides 6 years plus real 8-hourly funding rates. Used as a
  proxy, but a Binance result does not automatically transfer: ETH 4h
  `adx_trend` went from Sharpe 1.12 on Binance to -0.10 on Delta.
- **Alternative.me Fear & Greed**, free and keyless, daily from 2018. Read
  point-in-time via `strategies_v2._sentiment_at`, so no bar can see a reading
  published after it.

## Rejected, with reasons

- **1h timeframe.** Round-trip fees alone consume the intraday edge. Sweeps
  also time out on 2 CPU cores.
- **Sentiment strategies on BTC.** Sharpe -0.46.
- **FVG, BOS, CHoCH.** 0 of 22 and 0 of 15 configs profitable with enough
  trades to be meaningful.
- **A candle-break strategy from a YouTube walkthrough.** Mechanised, 62
  configs, 0 profitable.
- **`adx_trend_50_200` on 1d.** Sharpe 1.36 on 21 trades. A meaningless sample.

## Status

Research and backtesting only. No live trading, and no order executor exists
in this repository. Shadow mode reads public candles and logs signals.
