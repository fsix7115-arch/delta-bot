"""Detailed read-only account dump: every asset, every balance, raw values.

Never places an order. Secrets are not printed.
"""
import json
import sys

from check_api import load_env, get


def main():
    cfg = load_env()
    key = cfg["DELTA_API_KEY"]
    secret = cfg["DELTA_API_SECRET"]
    base = cfg["DELTA_BASE_URL"].rstrip("/")

    w = get(base, key, secret, "/v2/wallet/balances")
    print("=== WALLET ===")
    if not w.get("success"):
        print("failed:", w.get("error"))
        return 1
    # Delta returns a per-asset row. The perp products settle in INR, and the
    # INR value lives in the `*_inr` fields -- reading only `balance` reports
    # a USD figure that looks like zero for a small INR-only deposit.
    for asset in w["result"]:
        sym = asset.get("asset_symbol")
        bal = float(asset.get("balance", 0))
        avail = asset.get("available_balance")
        inr = float(asset.get("balance_inr", 0) or 0)
        avail_inr = float(asset.get("available_balance_inr", 0) or 0)
        blocked = float(asset.get("blocked_margin", 0) or 0)
        if bal == 0 and not inr:
            continue
        print(f"  {sym:6s} balance={bal:<16.10f} available={avail}")
        print(f"         INR value      = {inr:.2f}  (available {avail_inr:.2f})")
        if blocked:
            print(f"         blocked margin = {blocked:.6f}")
    inr_total = sum(float(a.get("available_balance_inr", 0) or 0)
                    for a in w["result"])
    usd_total = sum(float(a.get("available_balance", 0) or 0)
                    for a in w["result"])
    print(f"\n  TOTAL available USD  : {usd_total:.6f}")
    print(f"  TOTAL available INR  : {inr_total:.2f}")
    if inr_total <= 0 and usd_total <= 0:
        print("  -> NO funds available. Trading cannot start.")

    print("\n=== ASSETS (deposit status / KYC limits) ===")
    try:
        a = get(base, key, secret, "/v2/assets")
        if a.get("success"):
            for x in a["result"]:
                if x.get("deposit_status") == "enabled" and x.get("symbol") in (
                        "USD", "INR", "USDT", "BTC", "ETH"):
                    print(f"  {x.get('symbol'):6s} deposit={x.get('deposit_status')} "
                          f"min_dep={x.get('min_deposit_amount')} "
                          f"networks={[n.get('network') for n in x.get('networks') or []]}")
        else:
            print("  assets endpoint:", a.get("error"))
    except Exception as e:
        print("  assets failed:", e)

    print("\n=== PRODUCT (BTCUSD perp) ===")
    try:
        p = get(base, key, secret, "/v2/products/BTCUSD")
        r = p.get("result") or {}
        print(f"  id={r.get('id')} symbol={r.get('symbol')} "
              f"type={r.get('contract_type')}")
        print(f"  settling={r.get('settling_asset', {}).get('symbol')} "
              f"tick={r.get('tick_size')} size_increment={r.get('size_increment')}")
        print(f"  max_position={r.get('max_position_size')} state={r.get('state')}")
    except Exception as e:
        print("  products failed:", e)

    print("\n=== ORDERS / FILLS (read scope check) ===")
    for ep in ("/v2/orders", "/v2/fills", "/v2/positions"):
        try:
            r = get(base, key, secret, ep)
            n = len(r.get("result") or []) if r.get("success") else "-"
            print(f"  {ep:16s} success={r.get('success')} n={n} "
                  f"err={r.get('error') if not r.get('success') else ''}")
        except Exception as e:
            code = getattr(e, "code", "")
            print(f"  {ep:16s} HTTP {code} {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
