"""Find a Gemini model this key can actually call.

The key is valid (50 models listed) but several of them are gated for the
project's region/age and return 404 "no longer available to new users". This
probes the candidates and reports the first that answers.
"""
import json
import os
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
KEY = vals.get("GEMINI_API_KEY", "")

CANDIDATES = [
    "gemini-3.8-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash-lite",
    "gemini-2.5-pro", "gemini-2.0-flash", "gemma-4-31b-it",
]


def probe(model):
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        ":generateContent",
        data=json.dumps({"contents": [{"parts": [{"text": "Reply with only: OK"}]}]}).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = json.loads(r.read())
        txt = b["candidates"][0]["content"]["parts"][0]["text"]
        u = b.get("usageMetadata", {})
        print(f"  WORKS  {model}: {txt[:40]!r}  "
              f"in={u.get('promptTokenCount')} out={u.get('candidatesTokenCount')}")
        return True
    except urllib.error.HTTPError as e:
        msg = e.read()[:110].decode(errors="replace").replace("\n", " ")
        print(f"  {e.code}    {model}: {msg}")
    except Exception as e:
        print(f"  ERR    {model}: {type(e).__name__} {e}")
    return False


if __name__ == "__main__":
    print("probing models:")
    winner = None
    for m in CANDIDATES:
        if probe(m):
            winner = m
            break
    print()
    print(f"usable model: {winner}" if winner else "no candidate worked")
