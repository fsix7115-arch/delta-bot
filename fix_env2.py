import os
import stat

ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

with open(ENV) as f:
    raw = f.read().splitlines()

out = []
for line in raw:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        out.append(line)
        continue
    k, v = s.split("=", 1)
    # strip whitespace/quotes that crept in while pasting
    v = v.strip().strip('"').strip("'").strip()
    out.append(f"{k.strip()}={v}")
    print(f"  {k.strip():26s} len={len(v)}")

with open(ENV, "w") as f:
    f.write("\n".join(out) + "\n")
os.chmod(ENV, 0o600)
print("\nrewrote .env with stripped values")
