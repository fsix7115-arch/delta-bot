import numpy as np
import pandas as pd
import strategies_smc as M
from engine import load

# Build a tiny controlled dataset: one clean bullish impulse followed by a
# retest. A correct order-block detector must fire on the retest and NOT fire
# on bars where the move had not happened yet.
idx = pd.date_range("2024-01-01", periods=12, freq="4h", tz="UTC")
close = [100, 99, 98, 97,   96, 97, 100, 106, 112, 110, 109, 108]
high  = [101, 100, 99, 98,   97, 98, 101, 107, 113, 111, 110, 109]
low   = [ 99,  98, 97, 96,   95, 96,  99, 105, 111, 109, 108, 107]
op    = [100, 100, 99, 98,   97, 97,  99, 105, 111, 110, 110, 109]
df = pd.DataFrame({"open": op, "high": high, "low": low, "close": close,
                   "volume": [1.0]*12}, index=idx)
print(df.round(2).to_string())
sig = M.order_block_trade(df, impulse_atr=0.4, max_age=12, hold_bars=8)
print()
print("signal per bar:", sig.tolist())
print()
print("bars 0-5 are BEFORE the impulse. A leaking detector would already")
print("have queued an order block there. Only bar 7+ can know the impulse.")
