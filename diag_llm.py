"""Diagnose the two 403s without printing the keys.

Gemini 403 "unregistered callers" usually means the key was not sent as a
header. Groq 403 with "error code: 1010" is a Cloudflare block, not a bad key.
"""
import json
import os
import re
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

g = vals.get("GEMINI_API_KEY", "")
r = vals.get("GROQ_API_KEY", "")


def shape(v, kind):
    if not v:
        return f"{kind}: MISSING"
    head = v[:6] + "..." if kind == "GROQ" else v[:4] + "..."
    ws = "  <-- HAS WHITESPACE!" if v != v.strip() else ""
    return f"{kind}: len={len(v)} starts={head} prefix_ok={v.startswith(kind)}{ws}"


print(shape(g, "AIza"))
print(shape(r, "gsk_"))
print()

# --- Gemini: correct auth is the x-goog-api-key header -------------------
print("=== GEMINI via x-goog-api-key header ===")
req = urllib.request.Request(
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent",
    data=json.dumps({"contents": [{"parts": [{"text": "say OK"}]}]}).encode(),
    headers={"Content-Type": "application/json", "x-goog-api-key": g})
try:
    with urllib.request.urlopen(req, timeout=40) as resp:
        b = json.loads(resp.read())
    print("  OK", b["candidates"][0]["content"]["parts"][0]["text"][:80])
    print("  usage:", b.get("usageMetadata"))
except urllib.error.HTTPError as e:
    print(f"  FAIL {e.code}: {e.read()[:200].decode(errors='replace')}")
except Exception as e:
    print(f"  FAIL {type(e).__name__}: {e}")

# --- list models: does the key see ANY model at all? --------------------
print("=== GEMINI list models (key validity probe) ===")
req = urllib.request.Request(
    "https://generativelanguage.googleapis.com/v1beta/models",
    headers={"x-goog-api-key": g})
try:
    with urllib.request.urlopen(req, timeout=40) as resp:
        b = json.loads(resp.read())
    names = [m["name"] for m in b.get("models", [])][:6]
    print(f"  OK  {len(b.get('models', []))} models visible: {names}")
except urllib.error.HTTPError as e:
    print(f"  FAIL {e.code}: {e.read()[:200].decode(errors='replace')}")

# --- Groq: is it Cloudflare rather than auth? ---------------------------
print("=== GROQ diagnostics ===")
for label, url, hdrs in [
    ("models endpoint", "https://api.groq.com/openai/v1/models",
     {"Authorization": f"Bearer {r}"}),
    ("no-auth probe", "https://api.groq.com/openai/v1/models", {}),
]:
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=hdrs), timeout=30) as resp:
            print(f"  {label}: OK {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read()[:150].decode(errors="replace")
        print(f"  {label}: HTTP {e.code} {body}")
    except Exception as e:
        print(f"  {label}: {type(e).__name__} {e}")

print("  server:", urllib.request.urlopen(
    "https://api.groq.com/", timeout=15).read()[:120].decode(errors="replace")
    if True else "")
