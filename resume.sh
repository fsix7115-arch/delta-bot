#!/usr/bin/env bash
# Resume the Delta trading research in one shot.
# Usage:  bash ~/delta-bot/resume.sh
set -e
cd "$(dirname "$0")"

echo "=== 1. Engine tests (must be 11/11 before trusting anything) ==="
python3 test_engine.py 2>&1 | tail -3

echo
echo "=== 2. State summary ==="
python3 - <<'PY'
import pandas as pd, os
for f, label in (("results/sweep_6y.csv", "6y 4h+1d"),
                 ("results/sweep1h.csv", "6y 1h")):
    p = os.path.join("results", os.path.basename(f))
    if not os.path.exists(p):
        print(f"{label}: not run yet")
        continue
    d = pd.read_csv(p)
    ok = d[(d.oos_sharpe > 0.5) & (d.stress_sharpe > 0) & (d.oos_trades >= 15)]
    print(f"{label}: {len(d)} configs, {len(ok)} passed the bar")
    if len(ok):
        top = ok.iloc[0]
        print(f"   best: {top.symbol} {top.res} {top.strategy} stop={top.stop}")
        print(f"   Sharpe {top.oos_sharpe:.2f} | CAGR {top.oos_cagr*100:.1f}% "
              f"| DD {top.oos_dd*100:.1f}% | {int(top.oos_trades)} trades "
              f"| stress {top.stress_sharpe:.2f}")
PY

echo
echo "=== 3. Env status ==="
if [ -f .env ]; then
  echo ".env present (chmod $(stat -c %a .env))"
  grep -q '^DELTA_API_KEY=..' .env && echo "  key: SET" || echo "  key: EMPTY"
  grep '^DELTA_BASE_URL=' .env | sed 's/^/  /'
else
  echo ".env missing — copy .env.example to .env and fill it in"
  echo "  (testnet key from https://testnet.delta.exchange)"
fi

echo
echo "=== 4. Read STATE.md for full context ==="
