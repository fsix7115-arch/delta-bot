"""Look for the INR balance specifically.

The perp product settles in INR per Delta's docs, while /v2/wallet/balances
returns USD-denominated balances. An INR deposit may sit in a different place,
or may not be credited yet.
"""
import json
import sys

from check_api import load_env, get


def main():
    cfg = load_env()
    key, secret = cfg["DELTA_API_KEY"], cfg["DELTA_API_SECRET"]
    base = cfg["DELTA_BASE_URL"].rstrip("/")

    # 1) raw wallet, no filtering, so we can see every asset and balance field
    w = get(base, key, secret, "/v2/wallet/balances")
    print("=== RAW /v2/wallet/balances ===")
    print(json.dumps(w.get("result"), indent=1)[:1500])

    # 2) the transaction ledger shows deposits even when balance is not credited
    print("\n=== /v2/wallet/transactions (last 10) ===")
    try:
        t = get(base, key, secret, "/v2/wallet/transactions")
        res = t.get("result") or []
        print(f"success={t.get('success')} n={len(res)} err={t.get('error')}")
        for x in res[:10]:
            print(f"  {x.get('created_at')} type={x.get('type')} "
                  f"amount={x.get('amount')} asset={x.get('asset', {}).get('symbol')}")
    except Exception as e:
        print("  failed:", getattr(e, "code", e))

    # 3) spot balances, in case the INR landed as a spot holding
    print("\n=== /v2/spot/balances ===")
    try:
        s = get(base, key, secret, "/v2/spot/balances")
        print(f"success={s.get('success')} n={len(s.get('result') or [])}")
        for x in (s.get("result") or [])[:10]:
            print(f"  {x.get('symbol')} {x.get('balance')}")
    except Exception as e:
        print("  failed:", getattr(e, "code", e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
