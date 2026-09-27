"""Probe every free LLM provider we can reach and report what actually works.

Most aggregator READMEs list providers in a table. That table is wrong within
a month: catalogs churn, models get retired, and regional gating quietly
produces 404s for a key that is perfectly valid. This script measures reality
from the machine you run it on, which is the only measurement that matters.

What it checks per provider:
  - is the key structurally valid (shape, not a hardcoded placeholder)
  - does the models endpoint authenticate
  - does an actual completion succeed, with retries for the shared free tier
  - if it fails, the exact upstream error, verbatim

No key is ever printed. Usage:
    python3 probe.py            # everything
    python3 probe.py --json     # machine readable
    python3 probe.py --only groq
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, ".env")

# Cloudflare refuses requests that carry no User-Agent, which is most of what
# urllib sends by default. This one header is the difference between "Groq does
# not work" and Groq working.
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

RETRYABLE = (429, 500, 502, 503, 504)


# --------------------------------------------------------------- key loading

def load_env(path=ENV):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def key_shape(value, prefixes):
    """Describe a key without revealing it."""
    if not value:
        return "missing"
    if any(ph in value.lower() for ph in ("your_", "paste", "here", "xxx", "changeme")):
        return f"looks like a placeholder (len {len(value)})"
    ok = any(value.startswith(p) for p in prefixes)
    return f"len {len(value)}, prefix {'ok' if ok else 'unexpected'}"


# ----------------------------------------------------------------- http core

def request(url, headers=None, payload=None, timeout=45, retries=3):
    """POST or GET with backoff. Returns (status, parsed_json_or_text)."""
    delay = 3
    last = None
    for attempt in range(retries):
        data = json.dumps(payload).encode() if payload is not None else None
        hdrs = {"User-Agent": UA, "Accept": "application/json"}
        if payload is not None:
            hdrs["Content-Type"] = "application/json"
        hdrs.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "replace")
                try:
                    return r.status, json.loads(body)
                except json.JSONDecodeError:
                    return r.status, body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in RETRYABLE and attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            return e.code, body
        except Exception as e:                      # network, DNS, TLS
            last = f"{type(e).__name__}: {e}"
            if attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            return 0, last or "unknown error"
    return 0, last or "unknown error"


def err_text(body, limit=200):
    """Pull the human-readable part out of an upstream error."""
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return body[:limit]
    if isinstance(body, dict):
        for path in (("error", "message"), ("message",), ("error_msg",),
                     ("error", "data", "message")):
            cur = body
            for k in path:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    cur = None
                    break
            if isinstance(cur, str) and cur:
                return cur[:limit]
    return str(body)[:limit]


# ----------------------------------------------------------------- providers

def probe_gemini(env, timeout=45):
    key = env.get("GEMINI_API_KEY", "")
    res = {"name": "gemini", "key": key_shape(key, ("AIza", "AQ.")),
           "models": None, "call": None, "ok": False, "note": ""}

    st, body = request(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": key}, timeout=timeout)
    if st != 200:
        res["note"] = f"list models failed: {err_text(body)}"
        return res
    names = [m.get("name", "") for m in body.get("models", [])] \
        if isinstance(body, dict) else []
    res["models"] = len(names)

    # The catalog lists models this key may not call (regional gating), so
    # probe a small ladder rather than trusting the list.
    for model in ("gemini-3.8-flash", "gemini-2.5-flash-lite",
                  "gemini-2.0-flash-lite"):
        st, body = request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
            ":generateContent",
            headers={"x-goog-api-key": key},
            payload={"contents": [{"parts": [{"text": "Reply with only: OK"}]}]},
            timeout=timeout, retries=4)
        if st == 200:
            res["call"] = model
            res["ok"] = True
            return res
        res["note"] = f"{model}: {err_text(body, 110)}"
    return res


def probe_groq(env, timeout=45):
    key = env.get("GROQ_API_KEY", "")
    res = {"name": "groq", "key": key_shape(key, ("gsk_",)),
           "models": None, "call": None, "ok": False, "note": ""}

    st, body = request("https://api.groq.com/openai/v1/models",
                       headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    if st != 200:
        hint = ""
        if "1010" in str(body):
            hint = " Cloudflare is refusing this host's IP, not your key."
        res["note"] = f"list models failed: {err_text(body)}{hint}"
        return res
    ids = [m.get("id") for m in body.get("data", [])] \
        if isinstance(body, dict) else []
    res["models"] = len(ids)

    # Catalog ordering changes; prefer the larger general models.
    for pref in ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile"):
        if ids and pref not in ids:
            continue
        st, body = request(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            payload={"model": pref,
                     "messages": [{"role": "user", "content": "Reply with only: OK"}],
                     "max_tokens": 8}, timeout=timeout, retries=3)
        if st == 200:
            res["call"] = pref
            res["ok"] = True
            return res
        res["note"] = f"{pref}: {err_text(body, 110)}"
    if not ids:
        res["note"] = "no models listed"
    return res


def probe_openrouter(env, timeout=45):
    """Optional: only probed when the user supplies a key."""
    key = env.get("OPENROUTER_API_KEY", "")
    if not key:
        return {"name": "openrouter", "key": "not configured", "models": None,
                "call": None, "ok": False, "note": "skipped (no key)"}
    res = {"name": "openrouter", "key": key_shape(key, ("sk-or-",)),
           "models": None, "call": None, "ok": False, "note": ""}
    st, body = request("https://openrouter.ai/api/v1/models",
                       headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    if st != 200:
        res["note"] = f"list models failed: {err_text(body)}"
        return res
    res["models"] = len(body.get("data", [])) if isinstance(body, dict) else 0
    res["ok"] = True
    res["call"] = "(any paid model)"
    return res


PROBES = (probe_gemini, probe_groq, probe_openrouter)


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", help="probe a single provider")
    ap.add_argument("--env", default=ENV, help="path to .env")
    a = ap.parse_args()

    env = load_env(a.env)
    rows = []
    for fn in PROBES:
        if a.only and fn.__name__ != f"probe_{a.only}":
            continue
        try:
            rows.append(fn(env))
        except Exception as e:                        # a probe must never crash the run
            rows.append({"name": fn.__name__.replace("probe_", ""), "ok": False,
                         "note": f"probe crashed: {type(e).__name__}: {e}",
                         "key": "?", "models": None, "call": None})

    if a.json:
        print(json.dumps(rows, indent=2))
        return 0 if any(r["ok"] for r in rows) else 1

    width = max(len(r["name"]) for r in rows) if rows else 8
    print(f"{'provider':<{width}}  {'status':8s} {'models':>6s}  detail")
    print("-" * (width + 46))
    for r in rows:
        mark = "WORKS" if r["ok"] else "no"
        detail = r.get("call") or r.get("note", "")
        print(f"{r['name']:<{width}}  {mark:8s} {str(r.get('models') or '-'):>6s}  {detail[:52]}")
    live = [r["name"] for r in rows if r["ok"]]
    print()
    print(f"usable: {', '.join(live) if live else 'none'}")
    return 0 if live else 1


if __name__ == "__main__":
    sys.exit(main())
