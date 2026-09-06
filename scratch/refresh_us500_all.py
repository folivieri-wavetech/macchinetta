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
    print(f"\n================ REFRESH US 500 CASH PER {acc} ================")
    
    # Rimuovi file vecchi di US 500 Cash
    for tf in tfs:
        fpath = os.path.join(base_dir, f"candele_US_500_Cash_{tf}.json")
        if os.path.exists(fpath):
            os.remove(fpath)
            print(f"Rimosso vecchio file: {fpath}")
            
    # Scarica e salva da ES=F (24h continuous)
    for tf in tfs:
        c_yh = Motore_Trend.scarica_candele_yahoo("US 500 Cash", tf)
        if c_yh:
            Motore_Trend.salva_candele_locali("US 500 Cash", tf, c_yh)
            sub55 = c_yh[-55:]
            max_h = max(c['highPrice']['bid'] for c in sub55)
            min_l = min(c['lowPrice']['bid'] for c in sub55)
            kj = (max_h + min_l) / 2.0
            print(f"  [{tf:8s}] Ricevute {len(c_yh)} candele. Ultima: {c_yh[-1]['snapshotTime']} | Max={max_h:.2f} | Min={min_l:.2f} | ➡️ KJ55: {kj:.2f}")

    # Ricalcola Radar Trend
    os.chdir(base_dir)
    stato_file = os.path.join(base_dir, "stato_sistema.json")
    prezzi_live = {}
    if os.path.exists(stato_file):
        with open(stato_file) as f:
            prezzi_live = json.load(f).get("prezzi_live", {})
    mem_file = os.path.join(base_dir, "memoria_parametri.json")
    memoria = {}
    if os.path.exists(mem_file):
        with open(mem_file) as f:
            memoria = json.load(f)
    Motore_Trend.aggiorna_radar_trend(prezzi_live, memoria)
    print(f"✅ Radar Trend aggiornato per {acc}")
