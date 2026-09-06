import os
import sys
import glob
import json

sys.path.insert(0, '/data')
sys.path.insert(0, '/app')
sys.argv = ['Motore_Trend.py', 'FIORDOK_DEMO']

import Motore_Trend

tfs = ["MINUTE_5", "HOUR", "HOUR_4", "DAY"]
for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
    base_dir = f"/data/{acc}" if os.path.exists("/data") else acc
    os.chdir(base_dir)
    
    stato_file = os.path.join(base_dir, "stato_sistema.json")
    px_gold = 4427.5
    if os.path.exists(stato_file):
        with open(stato_file) as fp:
            px_gold = json.load(fp).get("prezzi_live", {}).get("Spot Gold", 4427.5)
            
    print(f"\n================ SALVATAGGIO CALIBRATO SPOT GOLD PER {acc} (Live = {px_gold}) ================")
    for tf in tfs:
        c = Motore_Trend.scarica_candele_yahoo("Spot Gold", tf, px_live=px_gold)
        if c:
            Motore_Trend.salva_candele_locali("Spot Gold", tf, c)
            sub55 = c[-55:]
            max_h = max(x["highPrice"]["bid"] for x in sub55)
            min_l = min(x["lowPrice"]["bid"] for x in sub55)
            kj = (max_h + min_l) / 2.0
            diff = px_gold - kj
            dir_pos = "Possibile LONG" if diff >= 0 else "Possibile SHORT"
            print(f"  [{tf:8s}] Ricevute {len(c):3d} candele (Da {sub55[0]['snapshotTime']} a {sub55[-1]['snapshotTime']})")
            print(f"            Max: {max_h:.1f} | Min: {min_l:.1f} | ➡️ KJ55: {kj:.1f} | Distanza: {abs(diff):.1f} pt ({dir_pos})")

    # Ricalcola Radar Trend
    mem_file = os.path.join(base_dir, "memoria_parametri.json")
    memoria = {}
    if os.path.exists(mem_file):
        with open(mem_file) as fp:
            memoria = json.load(fp)
    stato_f = os.path.join(base_dir, "stato_sistema.json")
    prezzi_l = {}
    if os.path.exists(stato_f):
        with open(stato_f) as fp:
            prezzi_l = json.load(fp).get("prezzi_live", {})
    prezzi_l["Spot Gold"] = px_gold
    Motore_Trend.aggiorna_radar_trend(prezzi_l, memoria)
    print(f"✅ Radar Trend salvato e aggiornato per {acc}")
