import os
import sys
import glob
import json
import zoneinfo
import datetime

sys.path.insert(0, '/data')
sys.path.insert(0, '/app')
sys.argv = ['Motore_Trend.py', 'FIORDOK_DEMO']

import Motore_Trend

tfs = ["MINUTE_5", "HOUR", "HOUR_4", "DAY"]

for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
    base_dir = f"/data/{acc}" if os.path.exists("/data") else acc
    print(f"\n================ RESET SPOT GOLD ESCLUSIVAMENTE SU IG PER {acc} ================")
    
    # Prendi prezzo live IG
    stato_file = os.path.join(base_dir, "stato_sistema.json")
    prezzi_live = {}
    if os.path.exists(stato_file):
        with open(stato_file) as f:
            prezzi_live = json.load(f).get("prezzi_live", {})
            
    px_gold = prezzi_live.get("Spot Gold") or 4426.5
    print(f"Prezzo live IG Spot Gold: {px_gold}")
    
    # Rimuovi vecchi file contaminati da CME
    for tf in tfs:
        fpath = os.path.join(base_dir, f"candele_Spot_Gold_{tf}.json")
        if os.path.exists(fpath):
            os.remove(fpath)
            print(f"Rimosso vecchio file: {fpath}")
            
    # Inizializza con buffer puro IG basato su px_live IG
    for tf in tfs:
        candele = Motore_Trend.carica_candele_locali("Spot Gold", tf, px_live=px_gold)
        kj = Motore_Trend.calcola_kj55_da_candele(candele, periods=55)
        print(f"  [{tf:8s}] Buffer IG inizializzato: {len(candele)} candele | ➡️ KJ55: {kj:.1f}")

    # Ricalcola Radar Trend
    os.chdir(base_dir)
    mem_file = os.path.join(base_dir, "memoria_parametri.json")
    memoria = {}
    if os.path.exists(mem_file):
        with open(mem_file) as f:
            memoria = json.load(f)
    Motore_Trend.aggiorna_radar_trend(prezzi_live, memoria)
    print(f"✅ Radar Trend aggiornato al 100% su IG per {acc}")
