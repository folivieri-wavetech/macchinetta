import json, os, time

def restore():
    # 1. Restore 30s
    with open("hyper_gold_state.json", "r", encoding="utf-8", errors="ignore") as f:
        c = f.read()

    d30 = None
    for i in range(len(c) - 1, 0, -1):
        if c[i] == "}":
            try:
                candidate = json.loads(c[:i+1])
                if candidate.get("position") is not None:
                    d30 = candidate
                    break
            except Exception:
                continue

    if d30:
        print("Restoring 30s state with Core LONG 5c @", d30["position"]["open_price"], "and", len(d30["increments"]), "increments")
        tmp = "hyper_gold_state.json.clean"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d30, f, indent=2)
        time.sleep(0.1)
        os.replace(tmp, "hyper_gold_state.json")
        print("30s RESTORED SUCCESSFULLY!")

    # 2. Restore M5
    with open("hyper_gold_m1_state.json", "r", encoding="utf-8", errors="ignore") as f:
        c = f.read()

    dm5 = None
    for i in range(len(c) - 1, 0, -1):
        if c[i] == "}":
            try:
                candidate = json.loads(c[:i+1])
                if candidate.get("position") is not None:
                    dm5 = candidate
                    break
            except Exception:
                continue

    if dm5:
        print("Restoring M5 state with Core SHORT 5c @", dm5["position"]["open_price"], "and", len(dm5["increments"]), "increments")
        tmp = "hyper_gold_m1_state.json.clean"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dm5, f, indent=2)
        time.sleep(0.1)
        os.replace(tmp, "hyper_gold_m1_state.json")
        print("M5 RESTORED SUCCESSFULLY!")

restore()
