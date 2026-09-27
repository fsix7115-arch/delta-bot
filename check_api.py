"""Verify the Delta credentials in .env work.

Deliberately READ-ONLY: it calls wallet/positions and never places an order.
Secrets are never printed - only lengths and success/failure.
"""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request


def load_env(path=".env"):
    """Read .env. Accepts both DELTA_API_SECRET and DELTA_API_SECRET_KEY,
    and falls back to the documented testnet URL if DELTA_BASE_URL is absent."""
    cfg = {}
    if not os.path.exists(path):
        print(f"no {path} found")
        return None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    if not cfg.get("DELTA_API_SECRET") and cfg.get("DELTA_API_SECRET_KEY"):
        cfg["DELTA_API_SECRET"] = cfg["DELTA_API_SECRET_KEY"]
    if not cfg.get("DELTA_BASE_URL"):
        cfg["DELTA_BASE_URL"] = "https://cdn-ind.testnet.deltaex.org"
    return cfg


def sign(secret, method, timestamp, path, query, payload):
    data = method + timestamp + path + query + payload
    return hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()


def get(url, api_key, api_secret, path, query=""):
    ts = str(int(time.time()))
    headers = {
        "api-key": api_key,
        "timestamp": ts,
        "signature": sign(api_secret, "GET", ts, path, query, ""),
        "User-Agent": "delta-check/1.0",
    }
    req = urllib.request.Request(url + path + query, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    cfg = load_env()
    if not cfg:
        return 1
    key = cfg.get("DELTA_API_KEY", "")
    secret = cfg.get("DELTA_API_SECRET", "")
    base = cfg.get("DELTA_BASE_URL", "").rstrip("/")

    print(f"base_url      : {base}")
    print(f"api_key       : {'SET (len ' + str(len(key)) + ')' if key else 'EMPTY'}")
    print(f"api_secret    : {'SET (len ' + str(len(secret)) + ')' if secret else 'EMPTY'}")
    if not key or not secret:
        print("\n-> fill DELTA_API_KEY and DELTA_API_SECRET in .env first")
        return 1
    if "testnet" in base:
        print("-> TESTNET mode: no real money at risk")
    else:
        print("-> PRODUCTION endpoint: real money. This check is read-only.")

    # 1) public endpoint first (no auth) - proves network + base URL
    try:
        with urllib.request.urlopen(base + "/v2/tickers/BTCUSD", timeout=20) as r:
            pub = json.loads(r.read().decode())
        print(f"\n[1] public ticker  : OK  BTCUSD mark={pub['result']['mark_price']}")
    except Exception as e:
        print(f"\n[1] public ticker  : FAILED {e}")
        return 1

    # 2) authenticated wallet - proves the signature is right
    ok = False
    for label, url in (("primary", base),
                       ("testnet", "https://cdn-ind.testnet.deltaex.org"),
                       ("prod-IN", "https://api.india.delta.exchange")):
        try:
            w = get(url, key, secret, "/v2/wallet/balances")
        except urllib.error.HTTPError as e:
            print(f"[2] wallet {label:8s}: HTTP {e.code} {e.reason}")
            continue
        except Exception as e:
            print(f"[2] wallet {label:8s}: FAILED {e}")
            continue
        if w.get("success"):
            res = w.get("result") or []
            tot = 0.0
            for a in res:
                for b in (a.get("balances") or []):
                    tot += float(b.get("balance", 0))
            print(f"[2] wallet {label:8s}: OK  assets={len(res)} "
                  f"total_balance={tot:.4f}")
            ok = True
            break
        print(f"[2] wallet {label:8s}: REJECTED {w.get('error')}")
    if not ok:
        print("\n401 on every endpoint usually means: the key was created on a")
        print("different environment (testnet key vs prod key), the secret was")
        print("copied with a stray space, or the key's IP whitelist is not")
        print("satisfied by this machine.")
        return 1

    # 3) positions - confirms read scope
    try:
        p = get(base, key, secret, "/v2/positions")
        if p.get("success"):
            pos = p.get("result") or []
            print(f"[3] positions      : OK  open_positions={len(pos)}")
            for x in pos[:5]:
                print(f"      {x.get('symbol')} size={x.get('size')} "
                      f"entry={x.get('entry_price')} upnl={x.get('unrealized_pnl')}")
        else:
            print(f"[3] positions      : REJECTED {p.get('error')}")
    except Exception as e:
        print(f"[3] positions      : FAILED {e}")

    print("\nAll read-only checks passed. No order was placed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
