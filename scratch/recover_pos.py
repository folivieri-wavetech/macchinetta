import json, sys

def recover(fname):
    print("=== RECOVERING", fname, "===")
    with open(fname, "r", encoding="utf-8", errors="ignore") as f:
        c = f.read()

    # Look for position and increments in the file
    for i in range(len(c) - 1, 0, -1):
        if c[i] == "}":
            try:
                d = json.loads(c[:i+1])
                pos = d.get("position")
                incs = d.get("increments", [])
                if pos is not None or len(incs) > 0:
                    print(f"Found non-empty state ending at {i}:")
                    print("Position:", pos)
                    print("Increments count:", len(incs))
                    for inc in incs:
                        print("  Inc:", inc)
                    print("Balance:", d.get("balance"))
                    print("Trading enabled:", d.get("trading_enabled"))
                    return d
            except Exception:
                continue
    return None

d30 = recover("hyper_gold_state.json")
dm5 = recover("hyper_gold_m1_state.json")
