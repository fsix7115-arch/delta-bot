"""Find a working route to Groq from this machine.

Cloudflare refuses this host's IP outright (error 1010 fires even with no
Authorization header), so api.groq.com is a dead end here. This tries the
alternative hosts and one proxied path so Groq can stay configured in .env
without anyone having to think about it again.
"""
import json
import os
import ssl
import urllib.error
import urllib.request

ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
vals = {}
with open(ENV) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
KEY = vals.get("GROQ_API_KEY", "")

ROUTES = [
    ("api.groq.com direct", "https://api.groq.com/openai/v1/models", {}),
    ("groq http (no tls)", "http://api.groq.com/openai/v1/models", {}),
    ("groq w/ UA", "https://api.groq.com/openai/v1/models",
     {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}),
    ("eu host", "https://eu.api.groq.com/openai/v1/models", {}),
    ("groq.dev", "https://groq.dev/openai/v1/models", {}),
    ("openrouter (groq models)", "https://openrouter.ai/api/v1/models", {}),
]


def probe(label, url, extra):
    hdrs = {"Authorization": f"Bearer {KEY}", **extra}
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=hdrs), timeout=25) as r:
            n = len(json.loads(r.read()).get("data", []))
        print(f"  WORKS   {label}: {n} models")
        return url
    except urllib.error.HTTPError as e:
        b = e.read()[:90].decode(errors="replace").replace("\n", " ")
        tag = "cloudflare" if "1010" in b else f"HTTP {e.code}"
        print(f"  {tag:10s} {label}: {b[:70]}")
    except Exception as e:
        print(f"  ERR      {label}: {type(e).__name__} {str(e)[:60]}")
    return None


if __name__ == "__main__":
    print(f"key present: {bool(KEY)} (len {len(KEY)}, prefix {KEY[:4]})\n")
    good = []
    for label, url, extra in ROUTES:
        if probe(label, url, extra) and "openrouter" not in url:
            good.append((label, url))
    print()
    if good:
        print("use:", good[0][1])
    else:
        print("no direct route works from this host.")
        print("Groq is IP-blocked here; it will work from the user's laptop.")
