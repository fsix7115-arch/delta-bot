ci: run the engine tests on every push

test_engine.py and test_lookahead.py are the two suites that matter: they
assert that a signal can only act on data available at its own timestamp.
Without them in CI, nothing stops a future edit from reintroducing lookahead
and the Sharpe numbers in the README stop meaning anything.

- Add .github/workflows/test.yml running both suites
- Add requirements-test.txt with the minimum versions needed
- Add status badges; fix the stale ARYX/delta-bot clone URL
- Ignore __pycache__ and .pytest_cache