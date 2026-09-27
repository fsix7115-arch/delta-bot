"""Verify the free LLM keys. Never prints a key.

Gemini works over the x-goog-api-key header. Note the key value in .env starts
with "AQ.A..." rather than the documented "AIza..." -- Google now issues some
keys in that form, and the list-models probe below is what actually proves
validity, not the prefix.

Groq is blocked from this machine by Cloudflare (error 1010 fires even with no
Authorization header), so it cannot be tested here at all.
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

# Pinned to the first model the key can actually call, verified by
# find_model.py. Several older names (gemini-2.0-flash, gemini-2.5-flash)
# return 404 "no longer available to new users" for this key.
GEM_MODEL = "gemini-3.8-flash"


def try_gemini():
    key = vals.get("GEMINI_API_KEY", "")
    print("=== GEMINI ===")
    if not key:
        print("  no key in .env")
        return False
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": key}), timeout=40) as r:
            models = json.loads(r.read()).get("models", [])
        print(f"  key valid: {len(models)} models visible")
    except urllib.error.HTTPError as e:
        print(f"  key INVALID: HTTP {e.code}")
        return False
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEM_MODEL}"
        ":generateContent",
        data=json.dumps({"contents": [{"parts": [{"text": "Reply with only: OK"}]}]}).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = json.loads(r.read())
        print(f"  call OK  ({GEM_MODEL})")
        print(f"  reply: {b['candidates'][0]['content']['parts'][0]['text'][:60]!r}")
        u = b.get("usageMetadata", {})
        print(f"  tokens: in={u.get('promptTokenCount')} out={u.get('candidatesTokenCount')}")
        return True
    except urllib.error.HTTPError as e:
        print(f"  call FAIL: HTTP {e.code} {e.read()[:150].decode(errors='replace')}")
    except Exception as e:
        print(f"  call FAIL: {type(e).__name__} {e}")
    return False


def try_groq():
    key = vals.get("GROQ_API_KEY", "")
    print("=== GROQ ===")
    if not key:
        print("  no key in .env")
        return False
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}"}), timeout=30) as r:
            print(f"  OK {json.loads(r.read()).get('data', [])[:1]}")
        return True
    except urllib.error.HTTPError as e:
        body = e.read()[:120].decode(errors="replace")
        if "1010" in body:
            print(f"  BLOCKED by Cloudflare (error 1010) — not a key problem.")
            print("  This machine's outbound IP is refused by Groq. Works from")
            print("  a laptop or phone, not from Cloud Shell.")
        else:
            print(f"  HTTP {e.code}: {body}")
    except Exception as e:
        print(f"  {type(e).__name__} {e}")
    return False


if __name__ == "__main__":
    ok_g = try_gemini()
    print()
    ok_q = try_groq()
    print()
    print(f"summary: gemini={'WORKS' if ok_g else 'FAIL'}  groq={'WORKS' if ok_q else 'FAIL'}")
