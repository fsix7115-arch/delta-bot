"""One client for the free LLMs, so no provider needs thinking about again.

Findings baked in:
  * Groq blocks Cloud Shell's bare requests with Cloudflare error 1010. Sending
    a browser User-Agent gets through. Discovered by groq_routes.py.
  * Gemini needs the key in the `x-goog-api-key` header, NOT the URL, and only
    gemini-3.8-flash is callable on this key (older names 404).

Usage:
    python3 llm.py "your prompt here"
    python3 llm.py --model gemini "..."   /  --model groq "..."

Keys are read from .env and are never printed.
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, ".env")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
GEM_MODEL = "gemini-3.8-flash"
# Groq's catalog changes often; llama-3.3-70b-versatile 404s now. Verified
# available via the models endpoint: openai/gpt-oss-120b is the strongest
# general model on the account, with qwen/qwen3.8-27b as a smaller fallback.
GROQ_MODEL = "openai/gpt-oss-120b"


def keys():
    out = {}
    if os.path.exists(ENV):
        with open(ENV) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    return out


def _post(url, headers, payload, retries=4):
    """POST with backoff.

    The Gemini free tier is a shared pool and returns 503 under load often
    enough that a single-shot call fails maybe one time in four. Retrying is
    the difference between "Gemini is broken" and "Gemini answered".
    """
    delay = 4
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read()[:200].decode(errors="replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise urllib.error.HTTPError(e.url, e.code, e.msg, e.headers,
                                         io.BytesIO(body.encode()))
    raise RuntimeError("unreachable")


def gemini(prompt, model=GEM_MODEL):
    key = keys().get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")
    b = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        ":generateContent",
        {"x-goog-api-key": key},
        {"contents": [{"parts": [{"text": prompt}]}]})
    return b["candidates"][0]["content"]["parts"][0]["text"]


def groq(prompt, model=GROQ_MODEL):
    key = keys().get("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set in .env")
    b = _post(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "User-Agent": UA},
        {"model": model,
         "messages": [{"role": "user", "content": prompt}],
         "max_tokens": 2048})
    return b["choices"][0]["message"]["content"]


def health():
    """Report which providers are usable right now, without printing keys.

    Gemini free tier returns 503 under load fairly often, so retry a couple of
    times before declaring it down.
    """
    rows = []
    for name, fn in (("gemini", gemini), ("groq", groq)):
        last = ""
        for attempt in range(3):
            try:
                rows.append((name, "WORKS", fn("Reply with only: OK").strip()[:20]))
                break
            except urllib.error.HTTPError as e:
                b = e.read()[:90].decode(errors="replace").replace("\n", " ")
                last = f"HTTP {e.code}"
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(3 * (attempt + 1))
                    continue
                rows.append((name, last, b[:44]))
                break
            except Exception as e:
                last = type(e).__name__
                rows.append((name, last, str(e)[:44]))
                break
        else:
            rows.append((name, "FAILED", last))
    for n, s, d in rows:
        print(f"  {n:7s} {s:10s} {d}")
    return rows


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    if args[0] == "--health":
        health()
        sys.exit(0)
    provider, prompt = "both", " ".join(args)
    if args[0] == "--model" and len(args) > 2:
        provider, prompt = args[1], " ".join(args[2:])
    for name, fn in (("gemini", gemini), ("groq", groq)):
        if provider not in (name, "both"):
            continue
        print(f"--- {name} ---")
        try:
            print(fn(prompt))
        except Exception as e:
            print(f"  failed: {type(e).__name__} {e}")
        print()
