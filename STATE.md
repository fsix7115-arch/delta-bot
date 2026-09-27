# PROJECT STATE — read this first in any new session.

## What this is
Delta Exchange India BTC/ETH perpetual futures research. Located at `~/delta-bot`.
Phase: research/backtest only. Live trading NOT started, NOT approved.

## Account status (verified against the live API)
- Production key works. Wallet **USD 0.4118 / INR 35.01**.
- `account_dump.py` reads `balance_inr` — the plain `balance` field is USD and
  reads as ~0 for an INR-only deposit. That caused a wrong "no funds" report.
- `/v2/positions` still 400s: the key has Read Data but **not Trading** scope.
- **Live trading is impossible right now**: $0.41 available vs Delta's ~$10
  minimum perp order, and the strategy needs ~$8 margin at a 2% stop.
- Shadow mode (`shadow.py`) is the active setup: logs signals, places no orders.
  Cron job `81116a955e5e` runs it every 4h and posts the signal here.
- `~/delta-bot/results/shadow_log.jsonl` accumulates every observation.

## Current best result

**Winner: order-block strategy on ETHUSD 4h** (Delta data, 2y)
- `strategies_smc.order_block_trade(impulse_atr=1.0, max_age=30, hold_bars=8)`, stop 2%
- OOS Sharpe **1.01**, 376 trades, CAGR +21%, max DD -16%, win rate 49%, PF 1.20
- Buy-and-hold ETH same window: **-21.6%** => alpha **+43%/yr**
- Monte Carlo (2000 bootstraps): P(loss) **12.2%**, p5 -12.6%, worst DD -31%
- This is the only config found with P(loss) under 15%.

**Previous leader, now demoted: `adx_trend_20_50` BTC 4h** (6y Binance)
- OOS Sharpe 0.79, 70 trades, CAGR +15.5%, P(loss) 28.2% — MARGINAL
- ETH 4h version of this FAILED on Delta data (Sharpe -0.10); the 6y Binance
  result did not transfer. Do not re-quote the 6y numbers as if they were
  live-venue results.

**Rejected:** BTC/ETH 1d `adx_trend_50_200` (21-23 trades, meaningless sample).
Stock Learners candle-break: 0/62 configs profitable with enough trades.

## Files
- `fetch_data.py` — Delta 2y candles (no key needed)
- `fetch_extended.py` — Binance 6y candles + real funding history
- `engine.py` — backtest engine (fees, slippage, stops, funding, no-lookahead)
- `strategies.py` — 20 signal generators
- `sweep.py` — walk-forward sweep, `SOURCE`/`RESOLUTIONS` env vars
- `test_engine.py` — **11/11 passing**, run this before trusting any result
- `.env.example` — template for API keys (user fills, chmod 600)
- `results/sweep_6y.csv` — 155 configs, 31 passed the bar

## Hard-won lessons (do not relearn these)
1. **Delta only serves ~2 years of candles.** 2020 crash and 2022 bear market
   are NOT available from Delta. Binance is the only source for 6y — but a
   Binance result does NOT transfer automatically (proved: ETH 4h adx_trend
   went from Sharpe 1.12 on Binance to -0.10 on Delta).
2. **`run()` must use `settled_t`, not `entry_t`, to bound the funding window.**
   Using entry_t re-counts every settlement each bar and produced a 5% drag
   instead of 0.1%. A test now catches this.
3. **qty is in units — P&L is `qty * (price - entry)`.** Dividing by entry again
   double-counts and produced absurd Sharpe values like -40.
4. **`metrics()` must NOT drop zero-return bars.** Filtering `r[r != 0]`
   removes the flat periods, shrinks the volatility denominator and inflates
   Sharpe without bound (produced Sharpe 680 on an 8-bar-hold strategy).
   `metrics()` now reports `raw_sharpe` and a `degenerate` flag for
   same-bar open/close artifacts (avg_bars < 1.5).
5. **Pattern detectors must tag the bar the pattern is KNOWN, not the bar it
   started.** An order block tagged at its own birth bar reads the impulse that
   has not printed yet — this leaked future data and produced Sharpe 60 with
   87% win rate. `test_lookahead.py` guards it now. Every stateful pattern
   needs a `hold_bars` so the engine does not open and close on the same bar.
6. Only 2 CPU cores. 1h sweeps time out repeatedly; 4h/1d finish in ~6 min.
7. Disk was 97% full; `npm cache clean --force` freed 1.3GB. Now ~69%.
8. Long sweeps need `timeout 2400`; the default 850s kills them.
9. `.env` must use exactly `DELTA_API_KEY` / `DELTA_API_SECRET`. The key in it
   is a PRODUCTION key (testnet + prod-IN 401, only prod-IN 200). Balance 0.
   Wallet reads work; `/v2/positions` 400s because the key lacks Trading scope.

## Next steps (in order)
1. ~~1h timeframe sweep~~ — running/complete, check `results/sweep1h.log`
2. **Delta cross-validation** — re-run the top strategy on Delta's own 2y data
   with real Delta fees. THIS MATTERS: all current numbers are Binance.
3. **Monte Carlo** — shuffle trade order, 1000 runs, check the strategy survives
4. Testnet paper trading (4-6 weeks) BEFORE any real money
5. Only then consider live, and only with per-trade approval

## Quick resume
New session: just say "Resume delta-bot", or run `bash ~/delta-bot/resume.sh`.
Everything needed is on disk — no need to re-explain anything.
The user has limited time (laptop may close), so keep state disk-persisted.

**Read `HANDOFF.md` first if you are a new agent.** It contains the full brief:
who the user is, the account facts (including the `balance_inr` trap), the
working strategy, the five bugs that produced fake results, what was already
tested and rejected, machine limits, and the ranked next steps.

## What the user has NOT approved
- Giving the API key (they asked for a .env template instead — done)
- Live trading
- Any real-money order

## Standing user instructions
- Check anything they send, improve it, warn and delete it if it's not usable
- Estimate time BEFORE starting any long task so they aren't disturbed
- They have limited time; leave state on disk so a new session resumes instantly
