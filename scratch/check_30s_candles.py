import json

d = json.load(open("hyper_gold_state.json", encoding="utf-8"))
candles = d.get("candles", [])
print(f"Total candles: {len(candles)}")

for c in candles:
    t = c.get("time", "")
    if t >= "15:45:00":
        o = c.get("open")
        h = c.get("high")
        l = c.get("low")
        cl = c.get("close")
        kj = c.get("kj55")
        tk = c.get("tk144")
        tk_bull = round(tk + 3.0, 2) if tk else None
        dist_kj = abs(cl - kj) if (cl is not None and kj is not None) else None
        dist_str = f"{dist_kj:.2f}" if dist_kj is not None else "--"
        print(f"{t}: O={o:.2f} H={h:.2f} L={l:.2f} C={cl:.2f} | KJ={kj} TK={tk} (TK+3={tk_bull}) | dist_kj={dist_str}")
