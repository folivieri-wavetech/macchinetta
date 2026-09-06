import os
import glob
import json
import sys

sys.path.insert(0, '/data')
sys.path.insert(0, '/app')
sys.argv = ['Motore_Trend.py', 'FIORDOK_DEMO']

import Motore_Trend

# 1. Trova e cancella tutti i file candele_Spot_Gold su tutta la PVC
all_files = glob.glob("/data/*/candele_Spot_Gold_*.json") + glob.glob("*/candele_Spot_Gold_*.json")
print("File da eliminare:", all_files)
for f in all_files:
    try:
        os.remove(f)
        print(f"Eliminato: {f}")
    except Exception as e:
        print(f"Errore eliminazione {f}: {e}")

# 2. Ricostruisci buffer puliti per tutti gli account usando il prezzo live reale di IG (~4426.2)
tfs = ["MINUTE_5", "HOUR", "HOUR_4", "DAY"]
for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
    base_dir = f"/data/{acc}" if os.path.exists("/data") else acc
    os.chdir(base_dir)
    
    stato_file = os.path.join(base_dir, "stato_sistema.json")
    px_live = 4426.2
    if os.path.exists(stato_file):
        with open(stato_file) as fp:
            px_live = json.load(fp).get("prezzi_live", {}).get("Spot Gold", 4426.2)
            
    print(f"\n--- Ricostruzione Spot Gold per {acc} (px_live IG = {px_live}) ---")
    for tf in tfs:
        candele = Motore_Trend.carica_candele_locali("Spot Gold", tf, px_live=px_live)
        kj = Motore_Trend.calcola_kj55_da_candele(candele, periods=55)
        print(f"  [{tf:8s}] Buffer: {len(candele)} candele | Ultima: {candele[-1]['snapshotTime']} | KJ55: {kj:.1f}")
        
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
    prezzi_l["Spot Gold"] = px_live
    Motore_Trend.aggiorna_radar_trend(prezzi_l, memoria)

print("\n✅ Reset e ricalcolo totale Spot Gold completati!")
