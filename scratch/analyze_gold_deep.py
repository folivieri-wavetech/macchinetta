import os
import glob
import json
from datetime import datetime

def analyze_file(filepath):
    with open(filepath) as f:
        candele = json.load(f)
    print(f"\n=======================================================")
    print(f"FILE: {filepath} (Totale candele: {len(candele)})")
    print(f"=======================================================")
    if not candele:
        print("Nessuna candela.")
        return
    
    # Check timestamps delta
    deltas = []
    for i in range(1, len(candele)):
        t1 = datetime.strptime(candele[i-1]['snapshotTime'], "%Y/%m/%d %H:%M:%S")
        t2 = datetime.strptime(candele[i]['snapshotTime'], "%Y/%m/%d %H:%M:%S")
        dt = (t2 - t1).total_seconds() / 60.0
        deltas.append(dt)
    
    print(f"Primo snapshotTime: {candele[0]['snapshotTime']}")
    print(f"Ultimo snapshotTime: {candele[-1]['snapshotTime']}")
    if deltas:
        print(f"Delta minuti tra candele: Min={min(deltas)}m, Max={max(deltas)}m, Mediana/Tipico={deltas[-1]}m")
    
    sub55 = candele[-55:]
    highs, lows, closes = [], [], []
    for c in sub55:
        h = c.get("highPrice", {})
        hv = h.get("mid") or h.get("bid") or h.get("ask") if isinstance(h, dict) else h
        l = c.get("lowPrice", {})
        lv = l.get("mid") or l.get("bid") or l.get("ask") if isinstance(l, dict) else l
        cl = c.get("closePrice", {})
        cv = cl.get("mid") or cl.get("bid") or cl.get("ask") if isinstance(cl, dict) else cl
        highs.append(float(hv))
        lows.append(float(lv))
        closes.append(float(cv))
    
    max_h = max(highs)
    min_l = min(lows)
    kj = (max_h + min_l) / 2.0
    
    print(f"\nAnalisi ultime 55 barre:")
    print(f"  Max High su 55 barre: {max_h:.2f}")
    print(f"  Min Low  su 55 barre: {min_l:.2f}")
    print(f"  Ultimo Close: {closes[-1]:.2f}")
    print(f"  ➡️ Kijun-sen (55) = ({max_h:.2f} + {min_l:.2f}) / 2 = {kj:.2f}")
    
    # Mostriamo le prime 3 e le ultime 5 barre delle 55
    print("\nUltime 5 barre:")
    for c in sub55[-5:]:
        t = c.get('snapshotTime')
        o = c.get('openPrice',{}).get('mid') or c.get('openPrice',{}).get('bid')
        h = c.get('highPrice',{}).get('mid') or c.get('highPrice',{}).get('bid')
        l = c.get('lowPrice',{}).get('mid') or c.get('lowPrice',{}).get('bid')
        cl = c.get('closePrice',{}).get('mid') or c.get('closePrice',{}).get('bid')
        print(f"  {t} | O: {o} | H: {h} | L: {l} | C: {cl}")

base_dir = "/data/FIORDOK_DEMO" if os.path.exists("/data/FIORDOK_DEMO") else "FIORDOK_DEMO"
for tf in ["MINUTE_5", "HOUR", "HOUR_4", "DAY"]:
    fpath = f"{base_dir}/candele_Spot_Gold_{tf}.json"
    if os.path.exists(fpath):
        analyze_file(fpath)
