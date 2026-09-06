import os
import glob
import json

def check_candles(filepath):
    with open(filepath) as f:
        candele = json.load(f)
    print(f"\n================ FILE: {filepath} ({len(candele)} candele) ================")
    invalid_count = 0
    valid_count = 0
    for i, c in enumerate(candele):
        h = c.get('highPrice', {})
        l = c.get('lowPrice', {})
        cl = c.get('closePrice', {})
        hv = h.get('mid') or h.get('bid') or h.get('ask') if isinstance(h, dict) else h
        lv = l.get('mid') or l.get('bid') or l.get('ask') if isinstance(l, dict) else l
        cv = cl.get('mid') or cl.get('bid') or cl.get('ask') if isinstance(cl, dict) else cl
        if hv is None or lv is None:
            print(f"Candela {i} INVALIDA: time={c.get('snapshotTime')} | H={h} | L={l} | C={cl}")
            invalid_count += 1
        else:
            valid_count += 1
    print(f"Valide: {valid_count}, Invalide: {invalid_count}")
    if valid_count > 0:
        valid_candles = [c for c in candele if (c.get('highPrice',{}).get('mid') or c.get('highPrice',{}).get('bid')) is not None]
        print(f"Ultime 5 valide:")
        for c in valid_candles[-5:]:
            print(f"  {c.get('snapshotTime')} | H={c.get('highPrice')} | L={c.get('lowPrice')} | C={c.get('closePrice')}")

for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
    for tf in ["MINUTE_5", "HOUR", "HOUR_4", "DAY"]:
        fp = f"/data/{acc}/candele_Spot_Gold_{tf}.json"
        if os.path.exists(fp):
            check_candles(fp)
