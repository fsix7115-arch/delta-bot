# COMPLETE HANDOFF — Delta Exchange Trading Research
# ==================================================
# If you are a NEW agent reading this: everything you need is below.
# Read STATE.md too — it has the live account status and current standings.

## 1. WHAT THE USER WANTS AND WHO THEY ARE

- **Language**: Hindi/English mix (Hinglish). Reply in Hinglish.
- **New to trading.** Does not know the markets. Explains things in simple
  words and expects plain answers, not jargon.
- **Limited time.** Their laptop may close at any moment, which kills the
  session. Everything is therefore persisted to disk, and a new session can
  resume in seconds.
- **The goal is NOT to get rich. The goal is that I "help them in trading"** —
  i.e. they want a partner doing the analysis while they look and learn.
- **Standing instructions** (they said these explicitly):
  1. Anything they send — check it, improve it, and if it is wrong, warn them
     and delete it.
  2. Find the best thing yourself; don't make them decide.
  3. Always tell them the ESTIMATED TIME before starting a long task, so they
     don't message in the middle and disrupt it.
  4. If they send something garbage, say so plainly. They respect that.
- They gave me a production Delta API key and a real (tiny) deposit. They
  repeatedly asked me to trade live. I declined to auto-trade. That boundary
  still stands and should be kept: **suggest the trade, show the numbers,
  let them approve.**

## 2. THE ACCOUNT (verified against the live API)

- `.env` holds `DELTA_API_KEY`, `DELTA_API_SECRET`, `DELTA_BASE_URL`.
  The key is a **PRODUCTION** key. `DELTA_BASE_URL=https://api.india.delta.exchange`.
- **Wallet: USD 0.4118 = INR 35.01.** That is all there is.
- CRITICAL: read `balance_inr` / `available_balance_inr`, NOT `balance`.
  `balance` is the USD figure and reads as ~0 for an INR-only deposit. This
  bug made me wrongly report "no funds" four times before I found it.
- `/v2/positions` returns **400** — the key has `Read Data` but NOT `Trading`
  scope. Wallet, orders and fills all return 200.
- **Live trading is impossible anyway:** $0.41 vs Delta's ~$10 minimum perp
  order, and the strategy wants ~$8 of margin at a 2% stop. Do not pretend
  otherwise.
- Product ids: **BTCUSD = 27, ETHUSD = 3136.** tick size 0.5.
- `.env` is chmod 600 and is protected from being read back. Never print the
  secret. `check_api.py` and `account_dump.py` are read-only and safe to run.

## 3. THE STRATEGY THAT ACTUALLY WORKS

**Order block (Smart Money Concepts), mechanised.**

- Code: `strategies_smc.py` → `order_block_trade(df, impulse_atr=1.0, max_age=30, hold_bars=8)`
- Venue/timeframe: **ETHUSD 4h on Delta**. Stop loss **2%**.
- Rule in plain words: a down-candle is tagged as an "order block" if the
  next 3 candles rally by more than 1×ATR. When price later trades back into
  that candle's body, go long. Stop is 2%, target is 3× that.

**Measured results, and which number to trust:**

| Test | Sharpe | Trades | Verdict |
|---|---|---|---|
| Delta, 2y (2024-09 → 2026-09) | **1.01** | 376 | the headline number |
| Binance, 6y (2020 → 2026) | **0.60** | 78 | **the honest number** |
| 2x / 3x cost stress | survives | | has headroom |
| Monte Carlo (2y) | P(loss) 11.3% | | acceptable |

**The 6-year Sharpe 0.60 is the one to quote.** The 1.01 is one favourable
2-year window. Always show both.

- **ETH only.** On BTC, buy-and-hold (29.6% CAGR) beats the strategy (6.5%).
  On ETH, the strategy wins (14% vs 3.2%). Do not deploy this on BTC.
- Buy-and-hold on ETH over the same 6y window was only +3.2% CAGR, so the
  strategy's edge on ETH is genuine, just modest.
- Sentiment-gated variant (`ob_sent_gate` in `hybrid.py`) looked spectacular on
  2y data (Sharpe 2.88, P(loss) 1.3%) but that is the max of 48 correlated
  trials on 41 trades. It has NOT been tested on 6y data. That test is the
  single most valuable next step.

## 4. THE FIVE BUGS I HIT — read these before trusting any number

Every one of these produced a spectacular, fake result. They are the reason
this project took a long time, and the reason early numbers in my messages
were wrong.

1. **P&L double-counted.** `qty` is already in units, so P&L is
   `qty * (price - entry)`. Dividing by `entry` again gave Sharpe values like
   -40. Fixed in `engine.run`.
2. **Funding double-counted.** The funding window must be bounded by
   `settled_t`, not `entry_t`, or every settlement is re-charged on every bar.
   Gave a 5% drag instead of 0.1%. `test_funding_*` tests guard it.
3. **Zero-return bars were being filtered out of the volatility calculation.**
   A strategy that sits flat has *low* volatility; removing those bars shrinks
   the denominator and inflates Sharpe without bound. This produced
   **Sharpe 680**. `metrics()` no longer drops zeros, and reports `raw_sharpe`
   plus a `degenerate` flag.
4. **Lookahead leak in the order-block detector.** The block was tagged at its
   own birth bar while using the *next* three candles to confirm the impulse —
   reading a move that had not happened yet. Produced 87% win rate and
   1643% CAGR. Fix: tag the block at bar `i+3`. `test_lookahead.py` guards it.
5. **Pattern signals were not held.** A pattern signal is an *entry event*, not
   a per-bar state. Without `hold_bars` the engine opened and closed on the
   same bar and skipped the round-trip cost entirely.

**Rule for any future strategy: if the Sharpe is above ~3, assume a bug until
proven otherwise.**

## 5. DATA SOURCES (all free, no key except where noted)

- `data/{SYMBOL}_{15m,1h,4h,1d}.csv` — Delta's own candles, ~2 years max.
  Delta simply does not serve older data; this is a hard limit.
- `data/extended/` — Binance 6-year candles + **real funding-rate history**
  (6574 rows per asset, 8-hourly). Needed because Delta exposes no funding
  history and only 2 years of price.
- `data/sentiment/fear_greed.csv` — Alternative.me Fear & Greed, 3156 daily
  readings from 2018, free and keyless. A published composite (volatility 25%,
  momentum 25%, social 15%, surveys 15% paused, dominance 10%, Google Trends
  10%). It is BTC-centric and market-wide, not per-coin.
- Sentiment is shifted in `_sentiment_at()` so a bar can only use a reading
  published before it. Keep that shift.
- **Live news headlines cannot be backtested honestly.** Today's headlines say
  nothing about 2022. If we want news-driven signals, it has to be a
  forward-looking shadow-mode feature, not a backtested edge.

## 6. WHAT WAS TESTED AND REJECTED — do not redo these

- **TradingAgents** (the repo the user sent): 22.9k lines, genuinely decent
  code with a real benchmark-alpha settlement loop. But it is equities-only
  (Yahoo Finance, SPY benchmark) and explicitly not a portfolio simulator. Its
  `settlement.py` idea is the one thing worth stealing later.
- **Stock Learners / the candle-break walkthrough**: mechanised in
  `strategies_youtube.py`, 62 configs, **0 profitable** with enough trades.
  The liquidity-sweep variant was flat 0.00 across all 32 configs.
- **ai4trade.ai**: an agent marketplace behind a login, not a strategy source.
  Could be a lead generator only.
- **FVG, BOS/CHoCH** in `strategies_smc.py`: 0/22 and 0/15 profitable.
- **1h timeframe**: structural failure, fees alone eat it. Sweeps time out
  repeatedly on 2 CPU cores.
- **Sentiment strategies on BTC**: -0.46 Sharpe. The F&G index is BTC-centric
  but does not predict BTC perps here; it worked on ETH.
- BTC 1d `adx_trend_50_200`: Sharpe 1.36 but only 21-23 trades. Meaningless
  sample. Rejected despite the headline number.

## 7. MACHINE AND OPERATIONAL NOTES

- **2 CPU cores only.** 4h/1d sweeps take ~6 min; 1h sweeps time out even at
  2400s. Prefer 4h/1d and small grids.
- **Disk was 97% full.** `npm cache clean --force` freed 1.3GB; now ~70%.
- Always run `python3 test_engine.py` first (11/11 passing) before trusting
  results, and `test_lookahead.py` after touching any pattern detector.
- `bash ~/delta-bot/resume.sh` prints tests + current best + env status.
- The user's laptop closing kills the session. **Shadow mode is scheduled on a
  cron job `81116a955e5e` every 4h** — it runs `shadow.py`, posts the current
  ETH 4h signal, and appends to `results/shadow_log.jsonl`. It places no
  orders.

## 8. SUGGESTED NEXT STEPS, IN ORDER

1. **Run the sentiment-gated hybrid on 6y Binance data.** This is the
   highest-value open question. `hybrid.py` has `ob_sent_gate`. If it holds
   ≥1.0 Sharpe on 6y, it becomes the primary strategy. Expect it to fall —
   that is a normal and useful outcome.
2. Test the winner on **BTC vs ETH separately** across more granular params to
   confirm the ETH-only finding rather than assuming it.
3. Add a **walk-forward parameter re-fit** (rolling in-sample window) instead
   of a single 55/45 split, so we can see how much the edge decays.
4. Only after 1-3: consider a **testnet** run (`https://cdn-ind.testnet.deltaex.org`,
   separate key). Not production.
5. Live trading requires: the user actually funding with a real amount
   (₹5,000+), Trading permission enabled, a persistent host (this Cloud Shell
   is ephemeral and would leave a position stranded if the session died), and
   per-trade approval.

## 9. TONE

The user is warm, calls me "bhai", and has limited time. Be direct, be
honest about bad numbers, and never pad a reply. When a result is
disappointing, say so plainly and show the next step rather than
apologising at length. They have said "don't make me decide, find the best
thing" — so bring a recommendation, not a menu, unless the decision is
genuinely theirs (like risking real money).
