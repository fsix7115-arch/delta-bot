#!/usr/bin/env bash
# One-command setup for anyone cloning this repo.
#
# Works for a human or for an AI agent. Installs dependencies, fetches the
# data (the .gitignore excludes it because it is ~13MB of regenerable output),
# and runs the test suite. If the tests fail, nothing downstream should be
# believed.
#
# Usage:  bash setup.sh
set -euo pipefail

cd "$(dirname "$0")"

say() { printf '\n=== %s ===\n' "$1"; }

say "1/4  dependencies"
python3 -c "import pandas, numpy" 2>/dev/null || {
  echo "installing pandas + numpy..."
  pip3 install --quiet pandas numpy
}

say "2/4  engine tests (must pass before any result means anything)"
python3 test_engine.py

say "3/4  lookahead regression test"
python3 test_lookahead.py

say "4/4  data"
mkdir -p data/extended data/sentiment
if [ ! -f data/ETHUSD_4h.csv ]; then
  echo "Delta candles (~2 years, no API key needed)..."
  python3 fetch_data.py
else
  echo "Delta candles already present"
fi
if [ ! -f data/extended/ETHUSD_4h.csv ]; then
  echo "Binance 6y candles + real funding rates (~6 min)..."
  python3 fetch_extended.py
else
  echo "extended data already present"
fi
if [ ! -f data/sentiment/fear_greed.csv ]; then
  echo "Fear & Greed index, 2018 to now..."
  python3 fetch_sentiment.py
else
  echo "sentiment data already present"
fi

say "done"
cat <<'EOF'
Next:
  SOURCE=binance python3 hybrid_6y.py    # the headline result (~5 min)
  python3 shadow.py                      # live signal, places no orders

If you are an AI agent: read README.md, then HANDOFF.md. The five bugs in
there are the part that matters -- they are the difference between a Sharpe
of 0.94 and a Sharpe of 680.

The original author's .env is NOT published. For the read-only API checks
(check_api.py, account_dump.py) supply your own Delta credentials in .env.
Trading permission is not needed and not wanted.
EOF
