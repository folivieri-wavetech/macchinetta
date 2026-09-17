import json

def check_file(fname):
    print("=== Checking", fname, "===")
    try:
        with open(fname, "r", encoding="utf-8") as f:
            c = f.read()
    except Exception as e:
        print("Cannot read:", e)
        return

    # Find valid json if there is extra data
    d = None
    try:
        d = json.loads(c)
    except Exception as e:
        print("Json load failed:", e)
        # Try finding last valid closing brace
        for i in range(len(c) - 1, 0, -1):
            if c[i] == "}":
                try:
                    d = json.loads(c[:i+1])
                    print("Recovered valid json ending at index", i)
                    break
                except Exception:
                    continue

    if d:
        print("Trading enabled:", d.get("trading_enabled"))
        print("Position:", d.get("position"))
        print("Increments:", len(d.get("increments", [])))
        print("Recent 10 trades:")
        for t in d.get("trades", [])[:10]:
            print(f"  {t.get('time')} | {t.get('action')} | PnL: {t.get('pnl')} | Reason: {t.get('reason')}")

check_file("hyper_gold_state.json")
check_file("hyper_gold_m1_state.json")
