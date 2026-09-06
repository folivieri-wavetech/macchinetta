import os
import glob
import json
from datetime import datetime

def calcola_kj_55(candele):
    if not candele or len(candele) < 55:
        return None
    sub = candele[-55:]
    highs, lows = [], []
    for c in sub:
        h = c.get("highPrice", {})
        hv = h.get("mid") or h.get("bid") or h.get("ask") if isinstance(h, dict) else h
        l = c.get("lowPrice", {})
        lv = l.get("mid") or l.get("bid") or l.get("ask") if isinstance(l, dict) else l
        if hv is not None and lv is not None:
            highs.append(float(hv))
            lows.append(float(lv))
    if len(highs) < 55:
        return None
    return (max(highs) + min(lows)) / 2.0

for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
    base_dir = f"/data/{acc}" if os.path.exists("/data") else acc
    print(f"\n==================== ACCOUNT: {acc} ====================")
    files = glob.glob(f"{base_dir}/candele_Spot*Gold*.json") + glob.glob(f"{base_dir}/candele_*GOLD*.json")
    for f in sorted(files):
        try:
            with open(f) as fp:
                d = json.load(fp)
            kj = calcola_kj_55(d)
            fname = os.path.basename(f)
            first_t = d[0].get("snapshotTime") if d else "N/A"
            last_t = d[-1].get("snapshotTime") if d else "N/A"
            last_c = d[-1].get("closePrice", {}) if d else {}
            
            # Calcolo min e max delle ultime 55 candele
            sub55 = d[-55:]
            max_55 = max(float(c.get('highPrice',{}).get('mid',0)) for c in sub55)
            min_55 = min(float(c.get('lowPrice',{}).get('mid',0)) for c in sub55)
            
            print(f"\n📁 {fname}:")
            print(f"   Candele: {len(d)} | Primo: {first_t} | Ultimo: {last_t}")
            print(f"   Ultimo Close: {last_c}")
            print(f"   Range 55 barre: Max = {max_55} | Min = {min_55}")
            print(f"   ➡️ Kijun-sen (55): {kj:.2f} (arrotondato a 1 dec: {round(kj, 1)})")
        except Exception as e:
            print(f"   Errore su {f}: {e}")
