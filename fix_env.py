import os
import stat

ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Confirmed from https://docs.delta.exchange/ :
#   Production India : https://api.india.delta.exchange   (india.delta.exchange keys)
#   Testnet India    : https://cdn-ind.testnet.deltaex.org (demo.delta.exchange keys)
# The key in .env authenticates against prod-IN, so write that.
PROD = "https://api.india.delta.exchange"
TESTNET = "https://cdn-ind.testnet.deltaex.org"

with open(ENV) as f:
    lines = [l.rstrip("\n") for l in f]

out, seen_secret, seen_url = [], False, False
for line in lines:
    s = line.strip()
    if s.startswith("DELTA_API_SECRET_KEY="):
        val = s.split("=", 1)[1].strip()
        out.append(f"DELTA_API_SECRET={val}")
        seen_secret = True
    elif s.startswith("DELTA_API_SECRET="):
        out.append(line)
        seen_secret = True
    elif s.startswith("DELTA_BASE_URL="):
        out.append(f"DELTA_BASE_URL={PROD}")
        seen_url = True
    else:
        out.append(line)

if not seen_secret:
    out.append("DELTA_API_SECRET=")
if not seen_url:
    out.append(f"DELTA_BASE_URL={PROD}")

# keep the risk guardrails present
if not any(l.startswith("DELTA_REQUIRE_APPROVAL=") for l in out):
    out += [
        "DELTA_MAX_RISK_PCT=0.5",
        "DELTA_MAX_DAILY_LOSS_PCT=2.0",
        "DELTA_REQUIRE_APPROVAL=true",
    ]

with open(ENV, "w") as f:
    f.write("\n".join(out) + "\n")

os.chmod(ENV, 0o600)
print("normalised .env")
print("  keys now:", [l.split("=", 1)[0] for l in out if l and not l.startswith("#")])
print("  mode:", oct(stat.S_IMODE(os.stat(ENV).st_mode)))
