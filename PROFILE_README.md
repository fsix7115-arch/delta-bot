# Fsix

Quantitative backtesting research for crypto perpetuals.

I build engines that are hard to fool, and I write down the ways I fooled
mine.

## What I'm working on

**[delta-bot](https://github.com/fsix7115-arch/delta-bot)** — a no-lookahead
backtesting engine for BTC/ETH perpetual futures on Delta Exchange India.

The current result: order block entries gated by crypto sentiment, on ETHUSD 1d,
Sharpe **0.94** out-of-sample over six years. It holds at 0.85 with costs
doubled. 129 trades, -14.9% maximum drawdown, against a buy-and-hold of +8.8%
over the same window.

That number is the smallest one worth quoting. The same strategy printed
Sharpe 2.88 on two years of data before the 2020 crash and 2022 bear market
were folded in. Both numbers are in the README, because a backtest that only
shows the flattering one is a sales pitch, not evidence.

## What I care about

Most of the work here is not finding strategies. It is finding the places where
a backtest lies to you:

- **Lookahead leaks.** A pattern detector that tags a block at its birth bar
  while reading the next three candles for confirmation. It produced an 87% win
  rate and a 1643% CAGR.
- **Volatility denominators that shrink.** Dropping zero-return bars from a
  Sharpe calculation makes a strategy that sits flat look brilliant. It
  produced Sharpe 680.
- **Costs that don't get charged.** Pattern signals with no holding period open
  and close on the same bar, skipping the round-trip fee entirely.

The rule I work by: if a Sharpe above 3 shows up, I assume a bug until I can
explain it.

## Tooling

Free-tier LLM routing across Gemini and Groq, with retry logic for the shared
free tier's 503s. The whole project runs on two CPU cores.

## Elsewhere

- Ask me about the bugs. That's the interesting part.
